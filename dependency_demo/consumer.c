/*
 * consumer.c
 *
 * This is the CONSUMER program.
 * It REQUIRES generated_config.h at compile time.
 *
 * If you try to compile this BEFORE running generate_config,
 * the compiler will produce a REAL error:
 *
 *   fatal error: generated_config.h: No such file or directory
 *
 * This is not simulated — it is a genuine compilation dependency.
 */

#include <stdio.h>
#include "generated_config.h"   /* <-- THIS IS THE DEPENDENCY */

int main(void) {
    printf("consumer: %s\n", GENERATED_MESSAGE);
    printf("consumer: generator version = %s\n", GENERATOR_VERSION);
    printf("consumer: build artifact flag = %d\n", BUILD_ARTIFACT);
    printf("consumer: compilation succeeded — generated_config.h was present at build time\n");
    return 0;
}
