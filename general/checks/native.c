/* Conformance probes, not a compiler-enforced purity system.
 * bad_* functions are intentional, legal impurity counterexamples. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

typedef struct {
    bool ok;
    uint32_t value;
} Result;

static Result add_value(uint32_t left, uint32_t right)
{
    if (right > UINT32_MAX - left) {
        return (Result){false, 0};
    }
    return (Result){true, left + right};
}

typedef struct {
    unsigned *value;
} Borrowed;

static unsigned bad_const_view(const Borrowed *view)
{
    /* A const struct view does not freeze its pointee. */
    *view->value += 1;
    return *view->value;
}

static unsigned ambient = 1;

static unsigned bad_hidden_read(unsigned input)
{
    return input + ambient;
}

int main(void)
{
    const uint32_t input = 12;
    const Result normal = add_value(input, 5);
    const Result edge = add_value(UINT32_MAX, 0);
    const Result overflow = add_value(UINT32_MAX, 1);
    if (!normal.ok || normal.value != 17 || input != 12) {
        return 1;
    }
    if (!edge.ok || edge.value != UINT32_MAX || overflow.ok) {
        return 2;
    }
    unsigned cell = 1;
    const Borrowed view = {&cell};
    if (bad_const_view(&view) != 2 || cell != 2) {
        return 3;
    }
    const unsigned first = bad_hidden_read(10);
    ambient = 2;
    if (first == bad_hidden_read(10)) {
        return 4;
    }
    puts("PASS: C value contracts and legal impurity counterexamples");
    return 0;
}
