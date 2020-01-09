//-------------------------------------------------------------------------
//  >>>>>>>>>>>>>>>>>>>>>>>>> COPYRIGHT NOTICE <<<<<<<<<<<<<<<<<<<<<<<<<
//-------------------------------------------------------------------------
//  Copyright (c) 2012 by Lattice Semiconductor Corporation      
// 
//-------------------------------------------------------------------------
// Permission:
//
//   Lattice Semiconductor grants permission to use this code for use
//   in synthesis for any Lattice programmable logic product.  Other
//   use of this code, including the selling or duplication of any
//   portion is strictly prohibited.
//
// Disclaimer:
//
//   This VHDL or Verilog source code is intended as a design reference
//   which illustrates how these types of functions can be implemented.
//   It is the user's responsibility to verify their design for
//   consistency and functionality through the use of formal
//   verification methods.  Lattice Semiconductor provides no warranty
//   regarding the use or functionality of this code.
//-------------------------------------------------------------------------
//
//    Lattice Semiconductor Corporation
//    5555 NE Moore Court
//    Hillsboro, OR 97124
//    U.S.A
//
//    TEL: 1-800-Lattice (USA and Canada)
//    503-268-8001 (other locations)
//
//    web: http://www.latticesemi.com/
//    email: techsupport@latticesemi.com
// 
//-------------------------------------------------------------------------
// 
//  Project  : iCE5 RGB LED Controller SPI interface
//  File Name: LED_control.v
// 
//  Description: 
//
//  Code Revision History :
//-------------------------------------------------------------------------
// Ver: | Author        | Mod. Date    |Changes Made:
// V1.0 | MDN           | 24-05-2014   |Initial version                             
//-------------------------------------------------------------------------
  

module LED_control (
                    // inputs
                    input   wire        clk27M,        // 27M clock
                    input   wire        rst,           // async reset
                    input               i_rgb_exe,
                    input   wire        i_rgb_den,
                    input [3:0]         i_rgb_addr,
                    input [7:0]         i_rgb_data,
                    output  reg         red_pwm,       // Red
                    output  reg         grn_pwm,       // Blue
                    output  reg         blu_pwm        // Green
                    );
    
    //------------------------------
    // INTERNAL SIGNAL DECLARATIONS: 
    //------------------------------

    parameter     LED_OFF   = 2'b00;
    parameter     RAMP_UP   = 2'b01;
    parameter     LED_ON    = 2'b10;
    parameter     RAMP_DOWN = 2'b11;

    parameter     on_max_cnt  = 22'h008000;  // 1 sec steady


    // wires (assigns)/ regs (always)
    reg [8:0] red_intensity;
    reg [8:0] grn_intensity;
    reg [8:0] blu_intensity;
    reg [9:0] clk_div_cnt;
    reg       clk32K;
    reg       update;
    reg [3:0] BreatheRamp_s;       
    reg [7:0] BlinkRate_s;

    reg [21:0] red_peak; // LED 'on' peak intensity (high precision)
    reg [21:0] grn_peak;
    reg [21:0] blu_peak;

    reg [21:0] off_max_cnt; // LED off duration
    reg [19:0] ramp_max_cnt; // LED ramp up/down duration
    reg [23:0] red_intensity_step; // LED intensity step when ramping
    reg [23:0] grn_intensity_step;
    reg [23:0] blu_intensity_step;

    reg [1:0] blink_state; // state variable
    reg [19:0] ramp_count; // counter for LED on/off duration
    reg [17:0] steady_count; // counter for LED ramp up/down duration

    reg [21:0] red_accum; // intensity accumulator during ramp
    reg [21:0] grn_accum;
    reg [21:0] blu_accum;

    reg [8:0] curr_red; // current LED intensity ( /256 = PWM duty cycle)
    reg [8:0] curr_grn;
    reg [8:0] curr_blu;

    reg [8:0] pwm_count;  // PWM counter
    reg [7:0] config_reg0_i ;
    reg [7:0] pre_scale_reg_i ;
    reg [7:0] on_time_reg_i ;
    reg [7:0] off_time_reg_i ;
    reg [7:0] breathe_on_reg_i ;
    reg [7:0] breathe_off_reg_i ;
    reg [7:0] pwm_red_reg_i ;
    reg [7:0] pwm_grn_reg_i ;
    reg [7:0] pwm_blu_reg_i ;
    reg       d1_update_i;
    reg       d2_update_i;
    reg       d3_update_i;
    reg       rgb_update_i;

    // Data registering based on address received from AP
    always @(posedge clk27M or posedge rst) begin
        if (rst) begin
            config_reg0_i <= 0;
            pre_scale_reg_i <= 0;
            on_time_reg_i <= 0;
            off_time_reg_i <= 8'd24;
            breathe_on_reg_i <= 8'hA5;
            breathe_off_reg_i <= 8'hA5;
            pwm_red_reg_i <= 8'h5F;
            pwm_grn_reg_i <= 8'h00;
            pwm_blu_reg_i <= 8'h00;
        end else begin
            if (i_rgb_den) begin
                case (i_rgb_addr)
                    4'h8 :
                        config_reg0_i <= i_rgb_data;
                    4'h9 :
                        pre_scale_reg_i <= i_rgb_data;
                    4'hA :
                        on_time_reg_i <= i_rgb_data;
                    4'hB :
                        off_time_reg_i <= i_rgb_data;
                    4'h5 :
                        breathe_on_reg_i <= i_rgb_data;
                    4'h6 :
                        breathe_off_reg_i <= i_rgb_data;
                    4'h1 :
                        pwm_red_reg_i <= i_rgb_data;
                    4'h2 :
                        pwm_grn_reg_i <= i_rgb_data;
                    4'h3 :
                        pwm_blu_reg_i <= i_rgb_data;
                endcase
            end else begin
                config_reg0_i <= config_reg0_i;
                pre_scale_reg_i <= pre_scale_reg_i;
                on_time_reg_i <= on_time_reg_i;
                off_time_reg_i <= off_time_reg_i;
                breathe_on_reg_i <= breathe_on_reg_i;
                breathe_off_reg_i <= breathe_off_reg_i;
                pwm_red_reg_i <= pwm_red_reg_i;
                pwm_grn_reg_i <= pwm_grn_reg_i;
                pwm_blu_reg_i <= pwm_blu_reg_i;
            end
        end
    end
    
    // Clock divider 
    // divides 27MHz to 32.768kHz
    // (basic PWM cycle)
    always @ (posedge clk27M or posedge rst)
        if (rst) begin
            clk_div_cnt  <= 0;
            clk32K  <= 0;
        end else begin
            if (clk_div_cnt >= (pre_scale_reg_i)) begin
                clk_div_cnt <= 0;
                clk32K <= ~clk32K;
            end else begin                       
                clk_div_cnt <= clk_div_cnt + 1;
            end
        end

    // Update signal
    always @(posedge clk32K or negedge i_rgb_exe) begin
        if (~i_rgb_exe)
            d1_update_i <= 0;
        else
            d1_update_i <= i_rgb_exe;
    end
        
    always @(posedge clk32K or posedge rst) begin
        if (rst) begin
            d2_update_i <= 0;
            d3_update_i <= 0;
            update <= 0;
        end else begin
            d2_update_i <= d1_update_i;
            d3_update_i <= d2_update_i;
            update <= d2_update_i && ~d3_update_i;
        end
    end
            
    // Capture stable parameters in local clock domain
    always @ (posedge clk32K or posedge rst)
        if (rst) begin
            BreatheRamp_s <= 4'b0000;
            BlinkRate_s   <= 8'd08;
            red_intensity <= 9'h00;
            grn_intensity <= 9'hFF;
            blu_intensity <= 9'hFF;
        end else begin
            if (update) begin
                BreatheRamp_s <= breathe_on_reg_i[3:0];
                BlinkRate_s   <= off_time_reg_i;
                red_intensity <= pwm_red_reg_i ;
                grn_intensity <= pwm_grn_reg_i ;
                blu_intensity <= pwm_blu_reg_i ;
            end
        end
    
    // Intensity values
    always @ (posedge clk32K or posedge rst)
        if (rst) begin
            red_peak <= 0;
            grn_peak <= 0;
            blu_peak <= 0;
        end else begin
            red_peak <= {red_intensity, 13'h0};
            grn_peak <= {grn_intensity, 13'h0};
            blu_peak <= {blu_intensity, 13'h0};
        end
    
    // interpret 'Blink rate' setting
    //   'off_max_cnt' is time spent in 'LED_OFF' states
    //   'step_shift' is used to scale the intensity step size.
    //   Stated period is blink rate with no ramp.  Ramping adds to the period.
    always @ (posedge clk32K or posedge rst)
        if (rst) begin
            off_max_cnt <= 22'h0 - 1;
        end else begin
            case (BlinkRate_s)
                8'h00:   begin off_max_cnt   <= 22'h000000; end
                8'd08:   begin off_max_cnt   <= 22'h000800; end // 1/16sec
                8'd16:   begin off_max_cnt   <= 22'h001000; end // 1/8 sec
                8'd24:   begin off_max_cnt   <= 22'h002000; end // 1/4 sec
                8'd32:   begin off_max_cnt   <= 22'h004000; end // 1/2 sec
                8'd40:   begin off_max_cnt   <= 22'h008000; end // 1 sec
                8'd48:   begin off_max_cnt   <= 22'h010000; end // 2 sec
                8'd56:   begin off_max_cnt   <= 22'h020000; end // 4 sec
                default: begin off_max_cnt   <= 22'h020000; end
            endcase
        end


    // interpret 'Breathe Ramp' setting
    //     'ramp_max_cnt' is time spent in 'RAMP_UP', RAMP_DOWN' states
    //     '***_intensity_step' is calculated to add to color accumulators each ramp step
    always @ (posedge clk32K or posedge rst)
        if (rst) begin
            ramp_max_cnt        <= 20'b0;
            red_intensity_step  <= 24'b0;
            grn_intensity_step  <= 24'b0;
            blu_intensity_step  <= 24'b0;
        end else begin
            case (BreatheRamp_s)
                4'b0000: begin
                    ramp_max_cnt   <= 20'h0;  // 0sec
                    red_intensity_step  <= 0 ;
                    grn_intensity_step  <= 0 ;
                    blu_intensity_step  <= 0 ;
                end
                4'b0001: begin
                    ramp_max_cnt   <= 20'h00400;  // 1/16sec
                    red_intensity_step  <= red_peak >> (10) ;
                    grn_intensity_step  <= grn_peak >> (10) ;
                    blu_intensity_step  <= blu_peak >> (10) ;
                end                 
                4'b0010: begin
                    ramp_max_cnt   <= 20'h00800;  // 1/8 sec
                    red_intensity_step  <= red_peak >> (11) ;
                    grn_intensity_step  <= grn_peak >> (11) ;
                    blu_intensity_step  <= blu_peak >> (11) ;                 
                end                 
                4'b0011: begin
                    ramp_max_cnt   <= 20'h01000;  // 1/4 sec
                    red_intensity_step  <= red_peak >> (12) ;
                    grn_intensity_step  <= grn_peak >> (12) ;
                    blu_intensity_step  <= blu_peak >> (12) ;                 
                end                 
                4'b0100: begin
                    ramp_max_cnt   <= 20'h02000;  // 1/2 sec
                    red_intensity_step  <= red_peak >> (13) ;
                    grn_intensity_step  <= grn_peak >> (13) ;
                    blu_intensity_step  <= blu_peak >> (13) ;                 
                end                 
                4'b0101: begin
                    ramp_max_cnt   <= 20'h04000;     // 1 sec
                    red_intensity_step  <= red_peak >> (14) ;
                    grn_intensity_step  <= grn_peak >> (14) ;
                    blu_intensity_step  <= blu_peak >> (14) ;                 
                end                 
                4'b0110: begin
                    ramp_max_cnt   <= 20'h08000;  // 2 sec
                    red_intensity_step  <= red_peak >> (15) ;
                    grn_intensity_step  <= grn_peak >> (15) ;
                    blu_intensity_step  <= blu_peak >> (15) ;                 
                end                 
                4'b0111: begin
                    ramp_max_cnt   <= 20'h10000;  // 4 sec
                    red_intensity_step  <= red_peak >> (16) ;
                    grn_intensity_step  <= grn_peak >> (16) ;
                    blu_intensity_step  <= blu_peak >> (16) ;                 
                end                 
                default: begin
                    ramp_max_cnt        <=  20'h10000;  // 4 sec
                    red_intensity_step  <= red_peak >> (16) ;
                    grn_intensity_step  <= grn_peak >> (16) ;
                    blu_intensity_step  <= blu_peak >> (16) ;
                end                 
            endcase
        end

    //  state machine to create LED ON/OFF/RAMP periods
    //   state machine is held (no cycles) if LED is steady state on/off
    //   state machine is reset to LED_ON state whenever parameters are updated.
    always @ (posedge clk32K or posedge rst)
        if (rst) begin
            blink_state <= LED_OFF;
            ramp_count   <= 20'b0;
            steady_count <= 18'b0;
        end else begin
            if(BlinkRate_s == 8'h00) begin
                blink_state <= LED_ON;
                ramp_count   <= 0;
                steady_count <= 0;
            end else if (update) begin
                blink_state <= LED_ON;
                ramp_count   <= 0;
                steady_count <= 0;
            end else begin
                case (blink_state)
                    LED_OFF:  begin
                        if(steady_count >= off_max_cnt) begin
                            ramp_count   <= 0;
                            steady_count <= 0;
                            blink_state <= RAMP_UP;
                        end else begin
                            steady_count <= steady_count + 1;
                        end
                    end
                    RAMP_UP:  begin
                        if(ramp_count >= ramp_max_cnt) begin
                            ramp_count   <= 0;
                            steady_count <= 0;
                            blink_state <= LED_ON;
                        end else begin
                            ramp_count <= ramp_count + 1;
                        end
                    end
                    LED_ON:  begin
                        if(steady_count >= on_max_cnt) begin
                            ramp_count   <= 0;
                            steady_count <= 0;
                            blink_state <= RAMP_DOWN;
                        end else begin
                            steady_count <= steady_count + 1;
                        end
                    end
                    RAMP_DOWN:  begin
                        if(ramp_count >= ramp_max_cnt) begin
                            ramp_count   <= 0;
                            steady_count <= 0;
                            blink_state <= LED_OFF;
                        end else begin
                            ramp_count <= ramp_count + 1;
                        end
                    end
                    default:  begin
                        blink_state <= LED_OFF;
                        ramp_count   <= 20'b0;
                        steady_count <= 18'b0;
                    end
                endcase
            end
        end


    // RampUP/DN accumulators
    always @ (posedge clk32K or posedge rst)
        if (rst) begin
            red_accum <= 22'b0;
            grn_accum <= 22'b0;
            blu_accum <= 22'b0;
        end else begin
            case (blink_state)
                LED_OFF:  begin
                    red_accum <= 0;
                    grn_accum <= 0;
                    blu_accum <= 0;
                end
                LED_ON:   begin
                    red_accum <= red_peak;
                    grn_accum <= grn_peak;
                    blu_accum <= blu_peak;
                end
                RAMP_UP:  begin
                    red_accum <= red_accum + red_intensity_step;
                    grn_accum <= grn_accum + grn_intensity_step;
                    blu_accum <= blu_accum + blu_intensity_step;
                end
                RAMP_DOWN: begin
                    red_accum <= red_accum - red_intensity_step;
                    grn_accum <= grn_accum - grn_intensity_step;
                    blu_accum <= blu_accum - blu_intensity_step;
                end
                default: begin
                    red_accum <= 0;
                    grn_accum <= 0;
                    blu_accum <= 0;
                end
            endcase
        end


    // set PWM duty cycle. 8-bit resolution 0x100 is 100% on
    always @ (posedge clk32K or posedge rst)
        if (rst) begin
            curr_red <= 9'h0FF;
            curr_grn <= 9'h0FF;
            curr_blu <= 9'b0;
        end else begin
            case (blink_state)
                LED_ON: begin
                    curr_red <= red_peak[21:13];
                    curr_grn <= grn_peak[21:13];
                    curr_blu <= blu_peak[21:13];
                end
                RAMP_UP: begin
                    curr_red <= red_accum[21:13];
                    curr_grn <= grn_accum[21:13];
                    curr_blu <= blu_accum[21:13];
                end
                RAMP_DOWN: begin
                    curr_red <= red_accum[21:13];
                    curr_grn <= grn_accum[21:13];
                    curr_blu <= blu_accum[21:13];
                end
                LED_OFF: begin
                    curr_red <= 0;
                    curr_grn <= 0;
                    curr_blu <= 0;
                end
                default: begin
                    curr_red <= 0;
                    curr_grn <= 0;
                    curr_blu <= 0;
                end
            endcase
        end

    // generate PWM outputs
    always @ (posedge clk32K or posedge rst)
        if (rst) begin
            pwm_count <= 9'b0;
            red_pwm   <= 0;
            grn_pwm   <= 0;
            blu_pwm   <= 0;
        end else begin
            if(pwm_count < 255)
                pwm_count <= pwm_count + 1;
            else
                pwm_count <= 0;
            
            if(pwm_count < curr_red)
                red_pwm <= 1;
            else
                red_pwm <= 0;

            if(pwm_count < curr_grn)
                grn_pwm <= 1;
            else
                grn_pwm <= 0;

            if(pwm_count < curr_blu)
                blu_pwm <= 1;
            else
                blu_pwm <= 0;  
        end

endmodule


