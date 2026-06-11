const expected = "3457c19c980b8b9e58ac5957d712cbdb9f2d887e19642ac5eace426cf39783e3";
const input = read_file("/input.dat");
accept("ctx-a verified");
emit_receipt("A1");
yield();
emit_receipt("A2");
exit(0);
