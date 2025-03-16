
static unsigned int enter_width = 24;
static unsigned int enter_height = 13;

/*  Call this macro repeatedly.  After each use, the pixel data can be extracted  */

#define ENTER_PIXEL(data,pixel) {\
pixel[0] = enter_header_data_cmap[(unsigned char)data[0]][0]; \
pixel[1] = enter_header_data_cmap[(unsigned char)data[0]][1]; \
pixel[2] = enter_header_data_cmap[(unsigned char)data[0]][2]; \
data ++; }

static unsigned char enter_header_data_cmap[3][3] = {
        {153,153,153},
        {255,255,255},
        {  0,  0,  0}
};
static unsigned char enter_header_data[] = {
        2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,
        2,2,2,2,2,2,2,2,
        2,2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,2,2,
        2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,2,
        2,0,0,0,1,1,1,1,1,0,0,0,0,0,0,0,
        0,0,1,0,0,0,0,2,
        2,0,0,0,1,0,0,0,0,0,0,0,0,0,0,0,
        0,0,1,0,0,0,0,2,
        2,0,0,0,1,0,0,0,0,0,0,1,1,1,1,0,
        0,1,1,1,1,0,0,2,
        2,0,0,0,1,1,1,1,1,0,0,1,0,0,0,1,
        0,0,1,0,0,0,0,2,
        2,0,0,0,1,0,0,0,0,0,0,1,0,0,0,1,
        0,0,1,0,0,0,0,2,
        2,0,0,0,1,0,0,0,0,0,0,1,0,0,0,1,
        0,0,1,0,0,0,0,2,
        2,0,0,0,1,1,1,1,1,0,0,1,0,0,0,1,
        0,0,1,1,1,0,0,2,
        2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,0,2,
        2,2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,
        0,0,0,0,0,0,2,2,
        2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,2,
        2,2,2,2,2,2,2,2
};
