try:
    import unittest2 as unittest
except ImportError:
    import unittest

import delta
import re
import time
import os
import threading
import signal
import sys
try:
    from io import StringIO
except ImportError:
    from StringIO import StringIO

class StringChunkTestCase(unittest.TestCase):
    def test_plain(self):
        c = delta.StringChunk(u'example')
        p = c.plain()
        self.assertEqual(p.static_str, u'example')

    def test_whitespace(self):
        c = delta.StringChunk(u'ex\nample')
        p = c.whitespace()
        self.assertEqual(p.static_str, u'  \n     ')

    def test_format(self):
        c = delta.StringChunk(u'example')
        values = list(u'abcd')
        self.assertEqual(c.format(values), u'example')
        self.assertEqual(values, list(u'abcd'))

    def test_as_regex(self):
        s = u'ex|amp[l]e'
        c = delta.StringChunk(s)
        rx = c.as_regex()
        self.assertEqual(rx, u'ex\\|amp\\[l\\]e')
        self.assertTrue(re.match(rx, s))


class NumberChunkTestCase(unittest.TestCase):
    def test_detect_int(self):
        c = delta.NumberChunk.detect(u'  ', u'999', False)
        self.assertEqual(c.format_str(), u' {0:+4}')

    def test_detect_float(self):
        c = delta.NumberChunk.detect(u'  ', u'999.99', False)
        self.assertEqual(c.format_str(), u' {0:+7.2f}')

    def test_detect_no_space(self):
        c = delta.NumberChunk.detect(u'', u'999', False)
        self.assertEqual(c.format_str(), u'{0:<+3}')

    def test_detect_no_space_first(self):
        c = delta.NumberChunk.detect(u'', u'999', True)
        self.assertEqual(c.format_str(), u'{0:+3}')

    def test_detect_leading_zeros_int(self):
        c = delta.NumberChunk.detect(u'', u'003', False)
        self.assertEqual(c.format_str(), u'{0:+03}')

    def test_detect_leading_zeros_float(self):
        c = delta.NumberChunk.detect(u'', u'003.99', False)
        self.assertEqual(c.format_str(), u'{0:+06.2f}')

    def test_detect_zero(self):
        c = delta.NumberChunk.detect(u'', u'0', False)
        self.assertEqual(c.format_str(), u'{0:<+1}')

    def test_detect_flex_int(self):
        c = delta.NumberChunk.detect(u' ', u'5', False, flex=True)
        self.assertEqual(c.format_str(), u' {0:+2}')

    def test_detect_no_flex_int(self):
        c = delta.NumberChunk.detect(u' ', u'5', False, flex=False)
        self.assertEqual(c.format_str(), u' {0:+1}')

    def test_detect_flex_float(self):
        c = delta.NumberChunk.detect(u' ', u'5.99', False, flex=True)
        self.assertEqual(c.format_str(), u' {0:+5.2f}')

    def test_detect_no_flex_float(self):
        c = delta.NumberChunk.detect(u' ', u'5.99', False, flex=False)
        self.assertEqual(c.format_str(), u' {0:+4.2f}')

    def test_plain(self):
        c = delta.NumberChunk.detect(u'  ', u'999', False)
        self.assertEqual(c.plain().format_str(), u' {0:4}')

    def test_colorize_positive(self):
        s = delta.NumberChunk.colorize(1, u'foo')
        self.assertEqual(s, u'\x1b[32mfoo\x1b[0m')

    def test_colorize_negative(self):
        s = delta.NumberChunk.colorize(-1, u'foo')
        self.assertEqual(s, u'\x1b[31mfoo\x1b[0m')

    def test_colorize_zero(self):
        s = delta.NumberChunk.colorize(0, u'foo')
        self.assertEqual(s, u'foo')

    def test_format_color(self):
        c = delta.NumberChunk.detect(u'  ', u'999', False)
        values = [1, 2, 3, 4]
        self.assertEqual(c.format(values, True), u'\x1b[32m   +1\x1b[0m')
        self.assertEqual(values, [2, 3, 4])

    def test_whitespace(self):
        c = delta.NumberChunk.detect(u'  ', u'999', False)
        self.assertEqual(c.whitespace().format([0], False), u'   +0')

    def test_as_regex(self):
        c = delta.NumberChunk.detect(u'  ', u'999', False)
        rx = re.compile(c.as_regex())
        self.assertTrue(rx.match('  999'))


class FormatTestCase(unittest.TestCase):
    def test_format(self):
        f = delta.Format([
            delta.StringChunk(u'hello'),
            delta.NumberChunk.detect(u' ', u'999', False),
        ])
        values = [1, 2, 3, 4]
        self.assertEqual(f.format(values), u'hello\x1b[32m  +1\x1b[0m')
        self.assertEqual(values, [1, 2, 3, 4])

    def test_format_no_colors(self):
        f = delta.Format([
            delta.StringChunk(u'hello'),
            delta.NumberChunk.detect(u' ', u'999', False),
        ])
        values = [1, 2, 3, 4]
        self.assertEqual(f.format(values, False), u'hello  +1')
        self.assertEqual(values, [1, 2, 3, 4])

    def test_format_no_colors(self):
        f = delta.Format([
            delta.StringChunk(u'hello'),
            delta.NumberChunk.detect(u' ', u'999', False),
        ])
        values = [1, 2, 3, 4]
        self.assertEqual(f.plain().format(values), u'hello   1')
        self.assertEqual(values, [1, 2, 3, 4])

    def test_format_whitespace(self):
        f = delta.Format([
            delta.StringChunk(u'hello'),
            delta.NumberChunk.detect(u' ', u'999', False),
        ])
        values = [1, 2, 3, 4]
        self.assertEqual(f.whitespace().format(values), u'     \x1b[32m  +1\x1b[0m')
        self.assertEqual(values, [1, 2, 3, 4])


class ParserTestCase(unittest.TestCase):
    def test_num_int(self):
        n = delta.Parser.num('999')
        self.assertEqual(n, 999)
        self.assertIsInstance(n, int)

    def test_num_float(self):
        n = delta.Parser.num('999.00')
        self.assertEqual(n, 999)
        self.assertIsInstance(n, float)

    def test_grouper(self):
        elts = range(1, 11)
        chunks = delta.Parser.grouper(elts, 3)
        chunks = list(chunks)
        self.assertListEqual(chunks, [
            (1, 2, 3),
            (4, 5, 6),
            (7, 8, 9),
            (10, None, None)])

    def test_parse_simple(self):
        parser = delta.Parser(use_colors=False)
        line = u'908638.24 1797254.54'
        fmt, deltas, values = parser.parse(line)
        self.assertEqual(fmt.format(values), line)
        self.assertIsNone(deltas)
        self.assertListEqual(values, [908638.24, 1797254.54])

    def test_parse_flex(self):
        parser = delta.Parser(use_colors=False)
        line = u'0.05 0.08 0.06 1/175 19537'
        fmt, deltas, values = parser.parse(line)
        self.assertEqual(fmt.format(values), u' 0.05  0.08  0.06  1/175 19537')

    def test_process_simple(self):
        parser = delta.Parser(use_colors=False)
        line = u'908638.24 1797254.54'
        fmt, deltas, values = parser.process(line)
        self.assertEqual(fmt.format(values), line)
        self.assertIsNone(deltas)
        self.assertListEqual(values, [908638.24, 1797254.54])

    def test_process_relative(self):
        parser = delta.Parser(use_colors=False)
        parser.process(u'1000')
        _, deltas, values = parser.process(u'1001')
        self.assertEqual(values, [1001])
        self.assertEqual(deltas, [1])
        _, deltas, values = parser.process(u'1002')
        self.assertEqual(values, [1002])
        self.assertEqual(deltas, [1])

    def test_process_absolute(self):
        parser = delta.Parser(absolute=True, use_colors=False)
        parser.process(u'1000')
        _, deltas, values = parser.process(u'1001')
        self.assertEqual(values, [1001])
        self.assertEqual(deltas, [1])
        _, deltas, values = parser.process(u'1002')
        self.assertEqual(values, [1002])
        self.assertEqual(deltas, [2])


class TestPrinter(delta.Printer):
    @classmethod
    def now(self):
        return u'NOW'


class PrinterTestCase(unittest.TestCase):
    def test_printer_simple(self):
        sio = StringIO()
        printer = TestPrinter(sio, timestamps=False, separators=False, orig=False, skip_zeros=False)
        f = delta.Format([
            delta.StringChunk(u'hello'),
            delta.NumberChunk.detect(u' ', u'999', False),
            delta.StringChunk(u'\n'),
        ], colors=False)
        printer.output(f.plain(), None, [999])
        printer.output(f, [1], [1000])
        printer.output(f, [0], [1000])
        printer.output(f, [-2], [998])

        self.assertEqual(sio.getvalue(), u'''hello 999
hello  +1
hello  +0
hello  -2
''')

    def test_printer_timestamps(self):
        sio = StringIO()
        printer = TestPrinter(sio, timestamps=True, separators=False, orig=False, skip_zeros=False)
        f = delta.Format([
            delta.StringChunk(u'hello'),
            delta.NumberChunk.detect(u' ', u'999', False),
            delta.StringChunk(u'\n'),
        ], colors=False)
        printer.output(f.plain(), None, [999])
        printer.output(f, [1], [1000])
        printer.output(f, [1], [1001])
        printer.output(f, [-2], [999])

        self.assertEqual(sio.getvalue(), u'''NOW: hello 999
NOW: hello  +1
NOW: hello  +1
NOW: hello  -2
''')

    def test_printer_timestamps_separators(self):
        sio = StringIO()
        printer = TestPrinter(sio, timestamps=True, separators=True, orig=False, skip_zeros=False)
        f = delta.Format([
            delta.StringChunk(u'hello'),
            delta.NumberChunk.detect(u' ', u'999', False),
            delta.StringChunk(u'\n'),
        ], colors=False)
        printer.output(f.plain(), None, [999])
        printer.output(f.plain(), None, [999])
        printer.separator()
        printer.output(f, [1], [1000])
        printer.output(f, [1], [1000])
        printer.separator()
        printer.output(f, [1], [1001])
        printer.output(f, [1], [1001])
        printer.separator()
        printer.output(f, [-2], [999])
        printer.output(f, [-2], [999])

        self.assertEqual(sio.getvalue(), u'''NOW: hello 999
NOW: hello 999
NOW
NOW: hello  +1
NOW: hello  +1
NOW
NOW: hello  +1
NOW: hello  +1
NOW
NOW: hello  -2
NOW: hello  -2
''')

    def test_printer_orig(self):
        sio = StringIO()
        printer = TestPrinter(sio, timestamps=False, separators=False, orig=True, skip_zeros=False)
        f = delta.Format([
            delta.StringChunk(u'hello'),
            delta.NumberChunk.detect(u' ', u'999', False),
            delta.StringChunk(u'\n'),
        ], colors=False)
        printer.output(f.plain(), None, [999])
        printer.output(f, [1], [1000])
        printer.output(f, [1], [1001])
        printer.output(f, [-2], [999])

        self.assertEqual(sio.getvalue(), u'''hello 999
hello 1000
       +1
hello 1001
       +1
hello 999
       -2
''')

    def test_printer_orig_no_values(self):
        sio = StringIO()
        printer = TestPrinter(sio, timestamps=False, separators=False, orig=True, skip_zeros=False)
        f = delta.Format([
            delta.StringChunk(u'hello\n'),
        ], colors=False)
        printer.output(f.plain(), None, [])
        printer.output(f, [], [])

        self.assertEqual(sio.getvalue(), u'''hello
hello
''')

    def test_printer_skipzeros(self):
        sio = StringIO()
        printer = TestPrinter(sio, timestamps=False, separators=False, orig=False, skip_zeros=True)
        f = delta.Format([
            delta.StringChunk(u'hello'),
            delta.NumberChunk.detect(u' ', u'999', False),
            delta.StringChunk(u'\n'),
        ], colors=False)
        printer.output(f.plain(), None, [999])
        printer.output(f, [1], [1000])
        printer.output(f, [0], [1000])
        printer.output(f, [-2], [998])

        self.assertEqual(sio.getvalue(), u'''hello 999
hello  +1
hello  -2
''')

    def test_printer_separators_single_line(self):
        sio = StringIO()
        printer = TestPrinter(sio, timestamps=False, separators=True, orig=False, skip_zeros=False)
        f = delta.Format([
            delta.StringChunk(u'hello'),
            delta.NumberChunk.detect(u' ', u'999', False),
            delta.StringChunk(u'\n'),
        ], colors=False)
        printer.separator()
        printer.output(f.plain(), None, [999])
        printer.separator()
        printer.output(f, [1], [1000])
        printer.separator()
        printer.output(f, [0], [1000])
        printer.separator()
        printer.output(f, [-2], [998])

        self.assertEqual(sio.getvalue(), u'''hello 999
hello  +1
hello  +0
hello  -2
''')

    def test_printer_separators_single_line_skip_zeros(self):
        sio = StringIO()
        printer = TestPrinter(sio, timestamps=False, separators=True, orig=False, skip_zeros=True)
        f = delta.Format([
            delta.StringChunk(u'hello'),
            delta.NumberChunk.detect(u' ', u'999', False),
            delta.StringChunk(u'\n'),
        ], colors=False)
        printer.separator()
        printer.output(f.plain(), None, [999])
        printer.separator()
        printer.output(f, [1], [1000])
        printer.separator()
        printer.output(f, [0], [1000])
        printer.separator()
        printer.output(f, [-2], [998])

        self.assertEqual(sio.getvalue(), u'''hello 999
hello  +1
--- NOW
hello  -2
''')

    def test_printer_separators_multiline(self):
        sio = StringIO()
        printer = TestPrinter(sio, timestamps=False, separators=True, orig=False, skip_zeros=False)
        f = delta.Format([
            delta.StringChunk(u'hello'),
            delta.NumberChunk.detect(u' ', u'999', False),
            delta.StringChunk(u'\n'),
        ], colors=False)
        printer.separator()
        printer.output(f.plain(), None, [999])
        printer.output(f.plain(), None, [99])
        printer.separator()
        printer.output(f, [1], [1000])
        printer.output(f, [1], [100])
        printer.separator()
        printer.output(f, [0], [1000])
        printer.output(f, [0], [100])
        printer.separator()
        printer.output(f, [-2], [998])
        printer.output(f, [-2], [98])

        self.assertEqual(sio.getvalue(), u'''hello 999
hello  99
--- NOW
hello  +1
hello  +1
--- NOW
hello  +0
hello  +0
--- NOW
hello  -2
hello  -2
''')


class FeedTestCase(unittest.TestCase):
    def test_fd_feed(self):
        def threadfunc(wfd):
            wfd.write(u'hello\n')
            wfd.flush()
            wfd.write(u'hello\n')
            wfd.flush()
            time.sleep(0.11)
            wfd.write(u'hello\n')
            wfd.flush()
            wfd.close()

        r, w = os.pipe()
        rfd = os.fdopen(r, u'r')
        wfd = os.fdopen(w, u'w')

        thd = threading.Thread(target=threadfunc, args=(wfd,))
        thd.start()

        feed = delta.fd_feed(rfd, 0.1)
        self.assertEqual(next(feed), u'hello\n')
        self.assertEqual(next(feed), u'hello\n')
        self.assertIs(next(feed), delta.separator)
        self.assertEqual(next(feed), u'hello\n')
        self.assertRaises(StopIteration, next, feed)

        thd.join()
        rfd.close()

    def test_command_feed(self):
        feed = delta.command_feed([u'/bin/echo', u'hello'], 0.1)
        self.assertIs(next(feed), delta.separator)
        self.assertEqual(next(feed), u'hello\n')
        self.assertIs(next(feed), delta.separator)
        self.assertEqual(next(feed), u'hello\n')
        self.assertIs(next(feed), delta.separator)
        self.assertEqual(next(feed), u'hello\n')

    def test_command_feed_count(self):
        feed = delta.command_feed([u'/bin/echo', u'hello'], 0.1, 2)
        self.assertIs(next(feed), delta.separator)
        self.assertEqual(next(feed), u'hello\n')
        self.assertIs(next(feed), delta.separator)
        self.assertEqual(next(feed), u'hello\n')
        self.assertRaises(StopIteration, next, feed)

    def test_command_feed_shell(self):
        feed = delta.command_feed((u'echo hello',), 0.1)
        self.assertIs(next(feed), delta.separator)
        self.assertEqual(next(feed), u'hello\n')
        self.assertIs(next(feed), delta.separator)
        self.assertEqual(next(feed), u'hello\n')
        self.assertIs(next(feed), delta.separator)
        self.assertEqual(next(feed), u'hello\n')


class UtilsTestCase(unittest.TestCase):
    def test_run(self):
        def threadfunc(wfd):
            wfd.write(u'hello 100\n')
            wfd.flush()
            wfd.write(u'hello 102\n')
            wfd.flush()
            time.sleep(0.11)
            wfd.write(u'hello 103\n')
            wfd.flush()
            wfd.close()

        r, w = os.pipe()
        rfd = os.fdopen(r, u'r')
        wfd = os.fdopen(w, u'w')

        thd = threading.Thread(target=threadfunc, args=(wfd,))
        thd.start()

        sio = StringIO()
        feed = delta.fd_feed(rfd, 0.1)
        parser = delta.Parser(flex=True, absolute=False, use_colors=False)
        printer = delta.Printer(sio, timestamps=False, separators=False, orig=False, skip_zeros=False)

        delta.run(feed, parser, printer)
        self.assertEqual(sio.getvalue(), u'''hello 100
hello  +2
hello  +1
''')

        thd.join()
        rfd.close()

    def test_use_separators(self):
        cases = {
            (u'true', u'always', False, False): True,
            (u'true', u'never', False, False): False,
            (u'true', u'auto', False, False): True,

            (None, u'always', False, False): True,
            (None, u'never', False, False): False,
            (None, u'auto', False, False): False,
            (None, u'auto', False, True): False,
            (None, u'auto', True, False): True,
            (None, u'auto', True, True): False,
        }
        for (cmd, separators, skip_zeros, timestamps), output in cases.items():
            self.assertEqual(delta.use_separators(cmd, separators, skip_zeros, timestamps), output) 

    def test_use_colors(self):
        r, w = os.pipe()
        rfd = os.fdopen(r, u'r')
        wfd = os.fdopen(w, u'w')

        rfd.close()
        self.assertTrue(delta.use_colors(u'always', wfd))
        self.assertFalse(delta.use_colors(u'never', wfd))
        self.assertFalse(delta.use_colors(u'auto', wfd))
        wfd.close()

        try:
            with open(u'/dev/tty') as fp:
                self.assertTrue(delta.use_colors(u'always', fp))
                self.assertFalse(delta.use_colors(u'never', fp))
                self.assertTrue(delta.use_colors(u'auto', fp))
        except IOError:
            pass


class CliTestCase(unittest.TestCase):

    def test_cli_stdin(self):
        stdin = StringIO(u'hello 1\nhello 2\nhello 3\n')
        stdout = StringIO()
        delta.real_cli(
            stdin=stdin,
            stdout=stdout,
            cmd=None,
            timestamps=False,
            interval=5,
            flex=True,
            separators=False,
            color=False,
            orig=False,
            skip_zeros=False,
            absolute=False,
            count=None)
        self.assertEqual(stdout.getvalue(), u'''hello  1
hello +1
hello +1
''')

    def test_cli_cmd(self):
        stdout = StringIO()
        delta.real_cli(
            stdin=StringIO(),
            stdout=stdout,
            cmd=('echo "hello 1"',),
            timestamps=False,
            interval=0.1,
            flex=True,
            separators=False,
            color=False,
            orig=False,
            skip_zeros=False,
            absolute=False,
            count=5)

        self.assertEqual(stdout.getvalue(), u'''hello  1
hello +0
hello +0
hello +0
hello +0
''')

if __name__ == '__main__':
    unittest.main()
