#include "i2ckbd.h"

i2c_kbd::i2c_kbd()
        :_master(I2C_KBD_MOD,I2C_KBD_SDA, I2C_KBD_SCL,0),
        c(0),
        _stat(0){
    _master.setSpeed(I2C_KBD_SPEED);//also inited
}

i2c_kbd::~i2c_kbd() {

}

int i2c_kbd::write_i2c_kbd() {
    unsigned char msg[2];
    msg[0] = 0x09;
    _master.i2cWrite(I2C_KBD_ADDR,msg,1);
    return 0;
}

int i2c_kbd::read_i2c_kbd() {
    uint16_t buff = 0;

    _master.i2cRead(I2C_KBD_ADDR,(uint8_t*)&buff,2);

    if(buff!=0) {
        return buff;
    }
    return -1;
}

int i2c_kbd::I2C_Send_RegData(int i2caddr, int reg, char command) {
    int retval;
    unsigned char I2C_Send_Buffer[2];
    I2C_Send_Buffer[0]=reg;
    I2C_Send_Buffer[1]=command;
    uint8_t I2C_Sendlen=2;

    retval = _master.i2cWrite(i2caddr,I2C_Send_Buffer,I2C_Sendlen);
    return retval;
}
