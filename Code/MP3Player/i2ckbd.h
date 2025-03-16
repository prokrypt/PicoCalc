#ifndef _I2C_KBD_H
#define _I2C_KBD_H

#include "task.h"
#include "gpio_rp2040.h"
#include "i2c_rp2040.h"

#define I2C_KBD_MOD 1
#define I2C_KBD_SDA 6
#define I2C_KBD_SCL 7
#define I2C_KBD_SPEED  400000
#define I2C_KBD_ADDR  0x1F

class i2c_kbd {
public:
    i2c_kbd();

    int write_i2c_kbd();
    int read_i2c_kbd();
    int I2C_Send_RegData(int i2caddr, int reg, char command);

    virtual ~i2c_kbd();
private:
     i2c_rp2040 _master;
     int c;
     int _stat;
};

#endif