/*
 * independent2.c
 *
 * An INDEPENDENT task — it has NO dependency on generated_config.h.
 * It can be compiled and run concurrently with other independent tasks.
 *
 * A small controlled delay is included so that concurrent execution
 * is visibly demonstrated in timing output.
 */

#include <stdio.h>

#ifdef _WIN32
  #include <windows.h>
  #define SLEEP_MS(ms) Sleep(ms)
#else
  #include <unistd.h>
  #define SLEEP_MS(ms) usleep((ms) * 1000)
#endif

int main(void) {
    printf("independent2: started\n");
    fflush(stdout);

    /* Controlled delay to make concurrent execution visible in timing */
    SLEEP_MS(700);

    printf("independent2: finished\n");
    fflush(stdout);
    return 0;
}
