
#include "backlight.h"

void lcd_backlight_update_reg() {

  uint8_t val;

  val = reg_get_value(REG_ID_BKL);
  val = val & 0xff;
  
  analogWriteFrequency(10000);
  analogWrite(PA8, val);

}

void lcd_backlight_update(int v) {
    int val = reg_get_value(REG_ID_BKL);

    if (v > 0) {
        if (val < 1)
            val = 1;
        else {
            val <<= 1;
            if (val > 255)
              val = 255;
        }
    } else if (v < 0) {
        if (val > 1) {
          if (val >= 255)
            val = 256;
          val >>= 1;
        }
    }

    analogWriteFrequency(10000);
    analogWrite(PA8, val);
    reg_set_value(REG_ID_BKL, val);
}

void kbd_backlight_update_reg(){

  uint8_t val;

  val = reg_get_value(REG_ID_BK2);
  val = val & 0xff;

  analogWriteFrequency(10000); 
  analogWrite(PC8, val);

}

void kbd_backlight_update_offset(){
  int val;
  val = reg_get_value(REG_ID_BK2);
  if(val == 0 )
    val = 16;
  else
    val *= 2;
  if (val > 256)
    val = 0;
  else if(val >128)
    val = 255;
 
  analogWriteFrequency(10000); 
  analogWrite(PC8, val);  
  reg_set_value(REG_ID_BK2,val);
}
