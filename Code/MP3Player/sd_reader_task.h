#ifndef SD_READER_TASK_H
#define SD_READER_TASK_H

#include <cstdint>
#include "task.h"
#include "lock_base_rp2040.h"
#include "mutex.h"
#include "condition_variable.h"
#include "ff.h"

class sd_reader_task : public task
{
public:
    sd_reader_task();

    void run() override;

    // Start the SD reading with a new file
    void start(FatFs * fs, FatFs::FILE * file);
    // Read some data from the file
    FatFs::FRESULT read_data(uint8_t* buff, uint16_t btr, uint16_t* br);
    // EOF handling
    inline bool eof() const {
        return _eof || _force_eof;
    }
    inline void force_eof() {
        _force_eof = true;
    }

private:

    FatFs *         _fs;       // FatFs object
    FatFs::FILE *   _file;     // MP3 file on SD

    uint8_t *       _req_buff;
    uint16_t        _req_btr;
    uint16_t *      _req_br;
    FatFs::FRESULT  _req_result;
    bool            _eof;
    bool            _force_eof;

    volatile bool                         _execute;
    mutex<lock_base_rp2040>               _execute_mutex;
    condition_variable<lock_base_rp2040>  _execute_cv;

    mutex<lock_base_rp2040>               _caller_mutex;
    condition_variable<lock_base_rp2040>  _caller_cv;
};

#endif // SD_READER_TASK_H
