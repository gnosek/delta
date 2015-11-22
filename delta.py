#!/usr/bin/env python

from __future__ import division, absolute_import, print_function

import re
import click
import sys
import time
import subprocess
import os
import colors
import string
import locale
try:
    from itertools import izip_longest
except ImportError: # python 3
    from itertools import zip_longest as izip_longest

if sys.version_info[0] == 2:
    import codecs
    _, encoding = locale.getdefaultlocale()
    sys.stdout = codecs.getwriter(encoding)(sys.stdout)

    if not hasattr(subprocess, 'check_output'):
        def check_output(cmd):
            return subprocess.Popen(cmd, stdout=subprocess.PIPE).communicate()[0]
        subprocess.check_output = check_output


separator = object()


class StringChunk(object):
    def __init__(self, static_str):
        self.static_str = static_str

    def plain(self):
        return self

    def whitespace(self):
        wsp = []
        for c in self.static_str:
            if c in string.whitespace:
                wsp.append(c)
            else:
                wsp.append(' ')
        return self.__class__(''.join(wsp))

    def format(self, values, use_colors=True):
        return self.static_str

    def as_regex(self):
        return re.escape(self.static_str)

    def __repr__(self):
        return "'{!r}'".format(self.static_str)


class NumberChunk(object):
    @staticmethod
    def detect(spaces, n, first, flex=True):
        prefix = u''
        align = u'<'
        plus = u'+'
        width = len(n)

        if spaces:
            prefix = u' '
            width += len(spaces) - 1
            align = u''
        elif first:
            align = u''

        if u'.' not in n:
            if align == u'' and flex and width < 2:
                width = 2
            if len(n) > 1 and n.startswith(u'0'):
                width = u'0{0}'.format(width)
                align = u''

            return NumberChunk(prefix, align, plus, width, u'')

        whole, frac = n.split(u'.', 1)
        frac_len = len(frac)
        if align == u'' and flex and width < frac_len + 3:
            width = frac_len + 3
        if len(whole) > 1 and whole.startswith(u'0'):
            width = u'0{0}'.format(width)
            align = u''
        return NumberChunk(prefix, align, plus, width, u'.%df' % len(frac))

    def __init__(self, prefix, align, plus, width, fmt):
        self.prefix = prefix
        self.align = align
        self.plus = plus
        self.width = width
        self.fmt = fmt

    def plain(self):
        return self.__class__(self.prefix, self.align, u'', self.width, self.fmt)

    def whitespace(self):
        return self

    def format_str(self):
        return u'%s{0:%s%s%s%s}' % (self.prefix, self.align, self.plus, self.width, self.fmt)

    def __repr__(self):
        return self.format_str()

    @staticmethod
    def colorize(val, s):
        if val is not None:
            if val > 0:
                return colors.green(s)
            elif val < 0:
                return colors.red(s)
        return s

    def format(self, values, use_colors=True):
        value = values.pop(0)
        s = self.format_str().format(value)
        if use_colors:
            s = self.colorize(value, s)
        return s

    def as_regex(self):
        return r'(\s*[0-9]+(?:\.[0-9]+)?)'


class Format(object):
    def __init__(self, chunks, colors=True):
        self.chunks = chunks
        self.colors = colors
        self.regex = re.compile(''.join(c.as_regex() for c in self.chunks))

    def plain(self):
        return self.__class__([c.plain() for c in self.chunks], False)

    def whitespace(self):
        return self.__class__([c.whitespace() for c in self.chunks], self.colors)

    def format_values(self, values, use_colors):
        values = list(values)
        if use_colors is None: use_colors = self.colors
        for chunk in self.chunks:
            yield chunk.format(values, use_colors)

    def format(self, values, use_colors=None):
        return ''.join(self.format_values(values, use_colors))

    def __repr__(self):
        return repr(self.chunks)


class Parser(object):
    def __init__(self, flex=True, absolute=False, use_colors=True):
        self.values = {}
        self.flex = flex
        self.absolute = absolute
        self.use_colors = use_colors

    @staticmethod
    def num(n):
        if u'.' not in n:
            return int(n)
        return float(n)

    @staticmethod
    def grouper(iterable, n, fillvalue=None):
        args = [iter(iterable)] * n
        return izip_longest(*args, fillvalue=fillvalue)

    def parse(self, line):
        values = []
        chunks = []

        elts = re.split(r'(\s*)([0-9]+(?:\.[0-9]+)?)', line)
        for i, (prefix, spaces, number) in enumerate(self.grouper(elts, 3)):
            if prefix:
                chunks.append(StringChunk(prefix))
            if number is not None:
                values.append(self.num(number))
                chunks.append(NumberChunk.detect(spaces, number, i==0 and not prefix))
                
        fmt = Format(chunks, self.use_colors)
        self.values[fmt] = values
        return fmt.plain(), None, values

    def process(self, line):
        for fmt, old_values in self.values.items():
            m = fmt.regex.match(line)
            if m:
                values = [self.num(v) for v in m.groups()]
                deltas = [n-o for n, o in zip(values, old_values)]
                if not self.absolute:
                    self.values[fmt] = values
                return fmt, deltas, values

        return self.parse(line)


class Printer(object):
    def __init__(self, fp, timestamps, separators, orig, skip_zeros):
        self.fp = fp
        self.timestamps = timestamps
        self.separators = separators
        self.orig = orig
        self.skip_zeros = skip_zeros
        self.separators_pending = 0
        self.lines_since_sep = 0
        self.multiline = False

    @classmethod
    def now(self):  # pragma: no cover
        return time.asctime()

    def separator(self):
        if self.separators:
            if self.lines_since_sep == 1:
                self.multiline = False
            self.separators_pending += 1

    def print_separator(self):
        fp = self.fp
        if self.timestamps:
            fp.write(u'{0}\n'.format(self.now()))
        else:
            fp.write(u'--- {0}\n'.format(self.now()))
        fp.flush()

    def print_separator_if_needed(self):
        if self.separators_pending == 0:
            self.multiline = True

        if self.separators_pending and (self.multiline or self.separators_pending > 1):
            self.print_separator()
            self.lines_since_sep = 0

        self.separators_pending = 0
        self.lines_since_sep += 1

    def do_print_line(self, line):
        fp = self.fp
        if self.timestamps:
            fp.write(u'{0}: '.format(self.now()))
        fp.write(line)
        fp.flush()

    def output(self, fmt, deltas, values):
        if deltas is None:
            self.print_separator_if_needed()
            self.do_print_line(fmt.format(values))
            return

        skip_delta = self.skip_zeros and all(d == 0 for d in deltas)

        if self.orig:
            self.print_separator_if_needed()
            if len(values):
                self.do_print_line(fmt.plain().format(values))
                if not skip_delta:
                    self.do_print_line(fmt.whitespace().format(deltas))
            else:
                self.do_print_line(fmt.format(values))
        else:
            if not skip_delta:
                self.print_separator_if_needed()
                self.do_print_line(fmt.format(deltas))


def stdin_feed(sep_interval):
    while True:
        ts = time.time()
        line = sys.stdin.readline()
        if sys.version_info[0] == 2:
            line = line.decode(encoding)
        if not line:
            break
        delta = time.time() - ts
        if delta > sep_interval:
            yield separator
        yield line


def command_feed(cmd, interval):
    _, encoding = locale.getdefaultlocale()
    if len(cmd) == 1:
        shell = os.getenv(u'SHELL', u'/bin/sh')
        cmd = (shell, u'-c') + cmd
    while True:
        output = subprocess.check_output(cmd)
        first = True
        for line in output.splitlines():
            if first:
                first = False
                yield separator
            yield line.decode(encoding) + u'\n'
        time.sleep(interval)


@click.command()
@click.option(u'-t/-T', u'--timestamps/--no-timestamps', help=u'Show timestamps on all output lines')
@click.option(u'-i', u'--interval', metavar=u'SECONDS', type=click.INT,
    help=u'Interval between command runs', default=1)
@click.option(u'-f/-F', u'--flex/--no-flex', help=u'Tweak column widths for better output (default is on)', default=True)
@click.option(u'--separators-auto', u'separators', flag_value=u'auto', help=u'Show chunk separators when needed (default)', default=True)
@click.option(u'-s', u'--separators', u'separators', flag_value=u'always', help=u'Always show chunk separators')
@click.option(u'-S', u'--no-separators', u'separators', flag_value=u'never', help=u'Never show chunk separators')
@click.option(u'-c', u'--color', type=click.Choice([u'never', u'auto', u'always']), help=u'Color output', default=u'auto')
@click.option(u'-o/-O', u'--orig/--no-orig', help=u'Show original output interleaved with deltas')
@click.option(u'-z/-Z', u'--skip-zeros/--with-zeros', help=u'Skip all-zero deltas')
@click.option(u'-a/-A', u'--absolute/--relative', help=u'Show deltas from original value, not last')
@click.argument(u'cmd', nargs=-1, required=False)
def cli(timestamps, cmd, interval, flex, separators, color, orig, skip_zeros, absolute):
    if cmd:
        feed = command_feed(cmd, interval)
        separators = separators != 'never'
    else:
        feed = stdin_feed(interval)
        separators = (
            separators == 'always' or
            (separators == 'auto' and skip_zeros and not timestamps))

    if color == u'never':
        color = False
    elif color == u'always':
        color = True
    else:
        color = os.isatty(sys.stdout.fileno())

    parser = Parser(flex, absolute, color)
    printer = Printer(sys.stdout, timestamps, separators, orig, skip_zeros)

    try:
        for line in feed:
            if line is separator:
                printer.separator()
                continue
            fmt, deltas, values = parser.process(line)
            printer.output(fmt, deltas, values)

    except KeyboardInterrupt:
        pass
    except IOError:
        return

if __name__ == u'__main__':
    cli()
