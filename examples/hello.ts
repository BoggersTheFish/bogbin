// hello.ts
const expected = "3457c19c980b8b9e58ac5957d712cbdb9f2d887e19642ac5eace426cf39783e3";
const input = read_file("/input.dat");
if (verify(input, expected)) {
    accept("hash matched and schema passed");
    emit_receipt("hello");
} else {
    reject("contradiction");
}
exit(0);
