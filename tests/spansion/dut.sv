module dut (
      input  wire                     clk
    , input  wire                     rst
    , input ext_spi_clk
    , input [6:0]s_axi_awaddr
    , input s_axi_awvalid
    , output s_axi_awready
    , input [31:0]s_axi_wdata
    , input [3:0]s_axi_wstrb
    , input s_axi_wvalid
    , output s_axi_wready
    , output [1:0]s_axi_bresp
    , output s_axi_bvalid
    , input s_axi_bready
    , input [6:0]s_axi_araddr
    , input s_axi_arvalid
    , output s_axi_arready
    , output [31:0]s_axi_rdata
    , output [1:0]s_axi_rresp
    , output s_axi_rvalid
    , input s_axi_rready
    , inout io0
    , inout io1
    , inout sck
    , inout ss
    , output ip2intc_irpt
);

    logic w_sck_i;
    logic w_sck_o;
    logic w_sck_t;
    logic w_ss_i;
    logic w_ss_o;
    logic w_ss_t;
    logic w_io0_i;
    logic w_io0_o;
    logic w_io0_t;
    logic w_io1_i;
    logic w_io1_o;
    logic w_io1_t;

//         for (i = 0; i < 4; i = i + 1) begin : g_qspi
//             IOBUF i_ja_iobuf (
//                   .I (w_qspi_d_out[i])
//                 , .IO(qspi_d[i])
//                 , .O (w_qspi_d_in[i])
//                 , .T (w_qspi_d_t[i])
//             );
//         end

    IOBUF i_sck_iobuf (
          .I (w_sck_o)
        , .IO(sck)
        , .O (w_sck_i)
        , .T (w_sck_t)
    );
    IOBUF i_ss_iobuf (
          .I (w_ss_o)
        , .IO(ss)
        , .O (w_ss_i)
        , .T (w_ss_t)
    );
    IOBUF i_io0_iobuf (
          .I (w_io0_o)
        , .IO(io0)
        , .O (w_io0_i)
        , .T (w_io0_t)
    );
    IOBUF i_io1_iobuf (
          .I (w_io1_o)
        , .IO(io1)
        , .O (w_io1_i)
        , .T (w_io1_t)
    );

    axi_quad_spi_1 i_axi_quad_spi_1 (
        .*
        , .s_axi_aclk (clk)
        , .s_axi_aresetn (rst)
        , .sck_i (w_sck_i)
        , .sck_o (w_sck_o)
        , .sck_t (w_sck_t)
        , .ss_i  (w_ss_i)
        , .ss_o  (w_ss_o)
        , .ss_t  (w_ss_t)
        , .io0_i (w_io0_i)
        , .io0_o (w_io0_o)
        , .io0_t (w_io0_t)
        , .io1_i (w_io1_i)
        , .io1_o (w_io1_o)
        , .io1_t (w_io1_t)
    );




endmodule
