/* A fixed getentropy()/getrandom() for the Godot import and export steps only (hmi_build.py
 * sets LD_PRELOAD for them). Godot seeds the generator behind scene node IDs and resource UIDs
 * from getentropy() alone (CryptoCore, MBEDTLS_NO_PLATFORM_ENTROPY), and gives every node of an
 * imported 3D model a random ID: the same tree then built to a different image each time
 * (2026-11-02). With a fixed stream it builds to the same bytes. Nothing in a build
 * step needs a secret; never preload this anywhere else.
 * Built with -nostdlib: no libc symbol, so no glibc version to match. */
#include <stddef.h>
#include <sys/types.h>

static unsigned long long state = 0x1d2c3b4a59687706ULL;

static unsigned long long next(void) {             /* splitmix64 */
    unsigned long long z = (state += 0x9e3779b97f4a7c15ULL);
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
    z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
    return z ^ (z >> 31);
}

static void fill(unsigned char *b, size_t n) {
    while (n) {
        unsigned long long v = next();
        for (int i = 0; i < 8 && n; i++, n--)
            *b++ = (unsigned char)(v >> (8 * i));
    }
}

int getentropy(void *buf, size_t len) { fill(buf, len); return 0; }

ssize_t getrandom(void *buf, size_t len, unsigned int flags) {
    (void)flags;
    fill(buf, len);
    return (ssize_t)len;
}
