/**
 * PicoCalc Keyboard Tester
 * https://www.clockworkpi.com/
 */
#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/gpio.h"
#include "hardware/clocks.h"
#include "i2ckbd.h"
#include "lcdspi.h"
#include "keyboard_define.h"

#include "uthash/include/uthash.h"

typedef struct {
    char name[10];
    char alias[10];
    uint8_t value;
} MyStruct;

typedef struct {
    int key;
    MyStruct data;
    UT_hash_handle hh;  // makes this structure hashable
} MapEntry;

MapEntry *map = NULL;
int total_cnt;

void add_entry(int key, const char* name, const char*alias, uint8_t value) {
    MapEntry *entry;

    HASH_FIND_INT(map, &key, entry);  // 检查是否已存在
    if (entry == NULL) {
        entry = (MapEntry*)malloc(sizeof(MapEntry));
        if (!entry) {
            fprintf(stderr, "Failed to allocate memory for entry\n");
            return;
        }
        entry->key = key;
        HASH_ADD_INT(map, key, entry);  // 添加到 hash 表
    }

    strncpy(entry->data.name, name, sizeof(entry->data.name) - 1);
    entry->data.name[sizeof(entry->data.name) - 1] = '\0';  // 保证以 null 结尾

    strncpy(entry->data.alias, alias, sizeof(entry->data.alias) - 1);
    entry->data.alias[sizeof(entry->data.alias) - 1] = '\0';  // 保证以 null 结尾

    entry->data.value = value;


}

MyStruct *get_entry(int key) {
    MapEntry *entry;
    HASH_FIND_INT(map, &key, entry);
    return entry ? &entry->data : NULL;
}
//
char *get_entry_name(int key) {
    MapEntry *entry;
    HASH_FIND_INT(map, &key, entry);
    if(entry != NULL) {
        if(entry->data.value == 0) {// unpressed
            return entry->data.alias;
        }else{
            return entry->data.name;
        }
    }else{
        printf("NULL in map\n");
    }
    return "NULL";
}



const uint LEDPIN = 25;

// 注意要 忽略大小写
int key_matrix[8][10] = {
        {KEY_UP,   KEY_F1,     KEY_F2,     KEY_F3,     KEY_F4,     KEY_F5,     KEY_NONE, KEY_NONE, KEY_NONE, KEY_NONE},
        {KEY_LEFT, KEY_RIGHT,  KEY_ESC,    KEY_TAB,    KEY_CAPS_LOCK, KEY_DEL, KEY_BACKSPACE, KEY_NONE, KEY_NONE, KEY_NONE},
        {KEY_DOWN, '`',        '/',        '\\',       '-',        '=',       '[',       ']',       KEY_NONE, KEY_NONE},
        {'1',      '2',        '3',        '4',        '5',        '6',       '7',       '8',       '9',      '0'},
        {'Q',      'W',        'E',        'R',        'T',        'Y',       'U',       'I',       'O',      'P'},
        {'A',      'S',        'D',        'F',        'G',        'H',       'J',       'K',       'L',      KEY_NONE},
        {'Z',      'X',        'C',        'V',        'B',        'N',       'M',       ',',       '.',      KEY_ENTER},
        {KEY_MOD_SHL, KEY_MOD_CTRL, KEY_MOD_ALT, ' ',  ';',        '\'',      KEY_MOD_SHR, KEY_NONE, KEY_NONE, KEY_NONE}
};


void init_kbd_map() {

    add_entry(KEY_UP, "UP","? ", 0);
    add_entry(KEY_F1, "F1", "? ", 0);
    add_entry(KEY_F2, "F2", "? ",0);
    add_entry(KEY_F3, "F3", "? ",0);
    add_entry(KEY_F4, "F4", "? ",0);
    add_entry(KEY_F5, "F5", "? ",0);

    add_entry(KEY_LEFT, "LF", "? ",0);
    add_entry(KEY_RIGHT, "RT", "? ",0);
    add_entry(KEY_ESC, "Esc", "?  ",0);
    add_entry(KEY_TAB, "Tab", "?  ",0);
    add_entry(KEY_CAPS_LOCK, "Caps", "?   ",0);
    add_entry(KEY_DEL, "Del","?  ", 0);
    add_entry(KEY_BACKSPACE, "Back", "?   ",0);

    add_entry(KEY_DOWN, "DN", "? ", 0);
    add_entry('`', "`","?", 0);
    add_entry('/', "/", "?",0);
    add_entry('\\', "\\","?", 0);
    add_entry('-', "-", "?",0);
    add_entry('=', "=", "?",0);
    add_entry('[', "[", "?",0);
    add_entry(']', "]", "?",0);

    add_entry('1', "1", "?",0);
    add_entry('2', "2", "?",0);
    add_entry('3', "3", "?",0);
    add_entry('4', "4", "?",0);
    add_entry('5', "5", "?",0);
    add_entry('6', "6", "?",0);
    add_entry('7', "7", "?",0);
    add_entry('8', "8", "?",0);
    add_entry('9', "9", "?",0);
    add_entry('0', "0", "?",0);

    add_entry('Q', "Q", "?",0);
    add_entry('W', "W", "?",0);
    add_entry('E', "E", "?",0);
    add_entry('R', "R", "?",0);
    add_entry('T', "T", "?",0);
    add_entry('Y', "Y", "?",0);
    add_entry('U', "U", "?",0);
    add_entry('I', "I", "?",0);
    add_entry('O', "O", "?",0);
    add_entry('P', "P", "?",0);

    add_entry('A', "A", "?",0);
    add_entry('S', "S", "?",0);
    add_entry('D', "D", "?",0);
    add_entry('F', "F", "?",0);
    add_entry('G', "G", "?",0);
    add_entry('H', "H", "?",0);
    add_entry('J', "J", "?",0);
    add_entry('K', "K", "?",0);
    add_entry('L', "L", "?",0);

    add_entry('Z', "Z", "?",0);
    add_entry('X', "X", "?",0);
    add_entry('C', "C", "?",0);
    add_entry('V', "V", "?",0);
    add_entry('B', "B", "?",0);
    add_entry('N', "N", "?",0);
    add_entry('M', "M", "?",0);
    add_entry(',', ",", "?",0);
    add_entry('.', ".", "?",0);
    add_entry(KEY_ENTER, "ENT", "?  ",0);

    add_entry(KEY_MOD_SHL, "Sft", "?  ",0);
    add_entry(KEY_MOD_CTRL, "Ctr", "?  ",0);
    add_entry(KEY_MOD_ALT, "Alt", "?  ",0);
    add_entry(' ', "Space", "?    ",0);
    add_entry(';', ";", "?",0);
    add_entry('\'', "'", "?",0);
    add_entry(KEY_MOD_SHR, "ShifR", "?    ",0);

}

void print_kbd_matrix_in_ascii() {
    char buf[64];
    /*
+------------------------------+
| UP    F1  F2   F3   F4   F5  |
+------------------------------+
|LF RT  Esc Tab Caps Del Back  |
+------------------------------+
| DN    `  /   \  -  =  [   ]  |
+------------------------------+
|1  2  3  4  5  6  7  8  9  0  |
+------------------------------+
|Q  W  E  R  T  Y  U  I  O  P  |
+------------------------------+
|A  S  D  F  G  H  J  K  L     |
+------------------------------+
|Z  X  C  V  B  N  M  ,  . ENT |
+------------------------------+
|Sft Ctr Alt  Space  ; ' ShifR |
+------------------------------+
 */
    lcd_reset_coords();
    printf("\n+===PicoCalc Keyboard Tester===+\n");
    lcd_print_string("+------------------------------+\n");
    sprintf(buf,        "| %s    %s  %s   %s   %s   %s  |\n", get_entry_name(KEY_UP),
                                                      get_entry_name(KEY_F1),
                                                      get_entry_name(KEY_F2),
                                                      get_entry_name(KEY_F3),
                                                      get_entry_name(KEY_F4),
                                                      get_entry_name(KEY_F5));

    lcd_print_string(buf);
    lcd_print_string("+------------------------------+\n");
    printf("%s", buf);
    printf("+------------------------------+\n");

    sprintf(buf,        "|%s %s  %s %s %s %s %s  |\n", get_entry_name(KEY_LEFT),
            get_entry_name(KEY_RIGHT),
            get_entry_name(KEY_ESC),
            get_entry_name(KEY_TAB),
            get_entry_name(KEY_CAPS_LOCK),
            get_entry_name(KEY_DEL),
            get_entry_name(KEY_BACKSPACE));
    lcd_print_string(buf);
    lcd_print_string("+------------------------------+\n");
    printf("%s", buf);
    printf("+------------------------------+\n");


    sprintf(buf,"| %s    %s  %s   %s  %s  %s  %s   %s  |\n", get_entry_name(KEY_DOWN),
            get_entry_name('`'),
            get_entry_name('/'),
            get_entry_name('\\'),
            get_entry_name('-'),
            get_entry_name('='),
            get_entry_name('['),
            get_entry_name(']'));
    lcd_print_string(buf);
    lcd_print_string("+------------------------------+\n");
    printf("%s", buf);
    printf("+------------------------------+\n");


    sprintf(buf,"|%s  %s  %s  %s  %s  %s  %s  %s  %s  %s  |\n", get_entry_name('1'),
            get_entry_name('2'),
            get_entry_name('3'),
            get_entry_name('4'),
            get_entry_name('5'),
            get_entry_name('6'),
            get_entry_name('7'),
            get_entry_name('8'),
            get_entry_name('9'),
            get_entry_name('0'));
    lcd_print_string(buf);
    lcd_print_string("+------------------------------+\n");
    printf("%s", buf);
    printf("+------------------------------+\n");


    sprintf(buf,"|%s  %s  %s  %s  %s  %s  %s  %s  %s  %s  |\n", get_entry_name('Q'),
            get_entry_name('W'),
            get_entry_name('E'),
            get_entry_name('R'),
            get_entry_name('T'),
            get_entry_name('Y'),
            get_entry_name('U'),
            get_entry_name('I'),
            get_entry_name('O'),
            get_entry_name('P'));
    lcd_print_string(buf);
    lcd_print_string("+------------------------------+\n");
    printf("%s", buf);
    printf("+------------------------------+\n");

    sprintf(buf,"|%s  %s  %s  %s  %s  %s  %s  %s  %s     |\n", get_entry_name('A'),
            get_entry_name('S'),
            get_entry_name('D'),
            get_entry_name('F'),
            get_entry_name('G'),
            get_entry_name('H'),
            get_entry_name('J'),
            get_entry_name('K'),
            get_entry_name('L'));
    lcd_print_string(buf);
    lcd_print_string("+------------------------------+\n");
    printf("%s", buf);
    printf("+------------------------------+\n");

    sprintf(buf,"|%s  %s  %s  %s  %s  %s  %s  %s  %s %s |\n", get_entry_name('Z'),
            get_entry_name('X'),
            get_entry_name('C'),
            get_entry_name('V'),
            get_entry_name('B'),
            get_entry_name('N'),
            get_entry_name('M'),
            get_entry_name(','),
            get_entry_name('.'),
            get_entry_name(KEY_ENTER));
    lcd_print_string(buf);
    lcd_print_string("+------------------------------+\n");
    printf("%s", buf);
    printf("+------------------------------+\n");


    sprintf(buf,"|%s %s %s  %s  %s %s %s |\n", get_entry_name(KEY_MOD_SHL),
            get_entry_name(KEY_MOD_CTRL),
            get_entry_name(KEY_MOD_ALT),
            get_entry_name(' '),
            get_entry_name(';'),
            get_entry_name('\''),
            get_entry_name(KEY_MOD_SHR));
    lcd_print_string(buf);
    lcd_print_string("+------------------------------+\n");
    printf("%s", buf);
    printf("+------------------------------+\n");

    if(total_cnt== KEYBOARD_OK_CNT) {
        lcd_print_string("\nKEYBOARD OK OK OK\n");
    }

}

int main() {
    char buf[64];
    set_sys_clock_khz(133000, true);
    stdio_init_all();

    uart_init(uart0, 115200);

    uart_set_format(uart0, 8, 1, UART_PARITY_NONE);  // 8-N-1
    uart_set_fifo_enabled(uart0, false);

    init_i2c_kbd();
    lcd_init();

    gpio_init(LEDPIN);
    gpio_set_dir(LEDPIN, GPIO_OUT);

    lcd_clear();
    //lcd_print_string("PicoCalc Keyboard Tester\n");
    gpio_put(LEDPIN, 1);
    sleep_ms(1000);

    //printf("PicoCalc Keyboard Tester\n");
    init_kbd_map();
    print_kbd_matrix_in_ascii();
    total_cnt = 0;
    while (1) {

        int c = lcd_getc(0);
        if(c != -1 && c > 0) {
            //lcd_putc(0,c);
            if(c >= 'a' && c <= 'z') {
                c = c  - ' ';
            }
            MyStruct *kb = get_entry(c);
            if( kb != NULL) {
                if(kb->value == 0) {
                    kb->value= 1;
                    total_cnt+=1;
                    //sprintf(buf,"Got %s\n",kb->name);
                    //printf(buf);
                    //lcd_print_string(buf);
                }else{
                    //printf("Pressed\n");
                    //lcd_print_string("Pressed!\n");
                }
            }
            print_kbd_matrix_in_ascii();

            if(total_cnt == KEYBOARD_OK_CNT) {
                printf("KEYBOARD OK OK OK OK OK\n");
            }
        }

        sleep_ms(40);
    }
}

