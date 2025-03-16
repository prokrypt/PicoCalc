
static unsigned int icon_p_width = 13;
static unsigned int icon_p_height = 13;

/*  Call this macro repeatedly.  After each use, the pixel data can be extracted  */

#define ICON_P_PIXEL(data,pixel) {\
pixel[0] = icon_p_header_data_cmap[(unsigned char)data[0]][0]; \
pixel[1] = icon_p_header_data_cmap[(unsigned char)data[0]][1]; \
pixel[2] = icon_p_header_data_cmap[(unsigned char)data[0]][2]; \
data ++; }

static unsigned char icon_p_header_data_cmap[3][3] = {
        {153,153,153},
        {255,255,255},
        {  0,  0,  0}
};
static unsigned char icon_p_header_data[] = {
        2,2,2,2,2,2,2,2,2,2,2,2,2,
        2,2,0,0,0,0,0,0,0,0,0,2,2,
        2,0,0,0,0,0,0,0,0,0,0,0,2,
        2,0,0,0,1,1,1,1,0,0,0,0,2,
        2,0,0,0,1,0,0,0,1,0,0,0,2,
        2,0,0,0,1,0,0,0,1,0,0,0,2,
        2,0,0,0,1,1,1,1,0,0,0,0,2,
        2,0,0,0,1,0,0,0,0,0,0,0,2,
        2,0,0,0,1,0,0,0,0,0,0,0,2,
        2,0,0,0,1,0,0,0,0,0,0,0,2,
        2,0,0,0,0,0,0,0,0,0,0,0,2,
        2,2,0,0,0,0,0,0,0,0,0,2,2,
        2,2,2,2,2,2,2,2,2,2,2,2,2
};
