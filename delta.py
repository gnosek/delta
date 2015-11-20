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

if sys.version_info[0] == 2:
    import codecs
    _, encoding = locale.getdefaultlocale()
    sys.stdout = codecs.getwriter(encoding)(sys.stdout)


separator = object()


class Format(object):
    def __init__(self, fmt, fmts, colors=True, **val_kwargs):
        self.fmt = fmt
        self.val_fmts = fmts
        self.colors = colors
        self.val_kwargs = val_kwargs

    def plain(self):
        return self.__class__(self.fmt, self.val_fmts, False, plus=u'')

    def __repr__(self):
        return self.fmt

    def colorize(self, val, fmt, use_colors=None, **kwargs):
        if use_colors is None: use_colors = self.colors
        s = fmt.format(val, **kwargs)
        if use_colors:
            if val > 0:
                return colors.green(s)
            elif val < 0:
                return colors.red(s)
        return s

    def format_values(self, *values):
        return [self.colorize(val, fmt, **self.val_kwargs) for fmt, val in zip(self.val_fmts, values)]

    def format(self, *values):
        return self.fmt.format(*self.format_values(*values))

    def format_str_with_spaces(self):
        last_seen = None
        fmt = []
        for c in self.fmt:
            if c == u'{':
                if last_seen == u'{': # escaped {
                    fmt.append(u' ')
                    last_seen = None
                    continue
            elif c == u'}':
                if last_seen == u'}': # escaped }
                    fmt.append(u' ')
                    last_seen = None
                    continue
                elif last_seen == u'{': # real format str
                    fmt.append(u'{}')
                    last_seen = None
                    continue
            elif c in string.whitespace:
                fmt.append(c)
            else:
                fmt.append(u' ')
            last_seen = c
        return u''.join(fmt)

    def format_wsp(self, *values, **kwargs):
        return self.format_str_with_spaces().format(*self.format_values(*values, **kwargs))


class ValueFormat(object):
    @staticmethod
    def detect(match, flex=True):
        spaces, n = match.groups()

        prefix = u''
        align = u'<'
        plus = u'+'
        width = len(n)

        if spaces:
            prefix = u' '
            width += len(spaces) - 1
            align = u''
        elif match.start(1) == 0:
            align = u''

        if u'.' not in n:
            if align == u'' and flex and width < 2:
                width = 2
            if len(n) > 1 and n.startswith(u'0'):
                width = u'0{}'.format(width)
                align = u''

            return ValueFormat(prefix, align, plus, width, u'')

        whole, frac = n.split(u'.', 1)
        frac_len = len(frac)
        if align == u'' and flex and width < frac_len + 3:
            width = frac_len + 3
        if len(whole) > 1 and whole.startswith(u'0'):
            width = u'0{}'.format(width)
            align = u''
        return ValueFormat(prefix, align, plus, width, u'.%df' % len(frac))

    def __init__(self, prefix, align, plus, width, fmt):
        self.prefix = prefix
        self.align = align
        self.plus = plus
        self.width = width
        self.fmt = fmt

    def format_str(self, prefix=None, align=None, plus=None, width=None, fmt=None):
        if prefix is None: prefix = self.prefix
        if align is None: align = self.align
        if plus is None: plus = self.plus
        if width is None: width = self.width
        if fmt is None: fmt = self.fmt
        return u'%s{:%s%s%s%s}' % (prefix, align, plus, width, fmt)

    def format(self, *values, **kwargs):
        return self.format_str(**kwargs).format(*values)


class Parser(object):
    def __init__(self, flex=True, absolute=False, use_colors=True):
        self.formats = {}
        self.values = {}
        self.flex = flex
        self.absolute = absolute
        self.use_colors = use_colors

    @staticmethod
    def num(n):
        if u'.' not in n:
            return int(n)
        return float(n)

    def parse(self, line):
        values = []
        val_formats = []
        def value(v):
            val = self.num(v.group(2))
            fmt = ValueFormat.detect(v, self.flex)
            values.append(val)
            val_formats.append(fmt)
            return u'{}'

        raw_fmt = line.replace(u'{', u'{{').replace(u'}', u'}}')
        raw_fmt = re.sub(r'(\s*)([0-9]+(?:\.[0-9]+)?)', value, raw_fmt)
        fmt = Format(raw_fmt, val_formats, self.use_colors)

        rx_line = re.sub(r'([()\[\]^$\\|])', r'\\\1', line)
        rx_str = re.sub(r'(\s*[0-9]+(?:\.[0-9]+)?)', r'(\s*[0-9]+(?:\.[0-9]+)?)', rx_line)
        rx = re.compile(rx_str)

        self.formats[rx] = fmt
        self.values[rx] = values

        return fmt.plain(), None, values

    def process(self, line):
        for rx, fmt in self.formats.items():
            m = rx.match(line)
            if m:
                old_values = self.values[rx]
                values = [self.num(v) for v in m.groups()]
                deltas = [n-o for n, o in zip(values, old_values)]
                if not self.absolute:
                    self.values[rx] = values
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

    def separator(self):
        if self.separators:
            if self.lines_since_sep == 1:
                self.multiline = False
            self.separators_pending += 1

    def print_separator(self):
        fp = self.fp
        if self.timestamps:
            fp.write(u'{}\n'.format(time.asctime()))
        else:
            fp.write(u'--- {}\n'.format(time.asctime()))
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
            fp.write(u'{}: '.format(time.asctime()))
        fp.write(line)
        fp.flush()

    def output(self, fmt, deltas, values):
        if deltas is None:
            self.print_separator_if_needed()
            self.do_print_line(fmt.format(*values))
            return

        skip_delta = self.skip_zeros and all(d == 0 for d in deltas)

        if self.orig:
            self.print_separator_if_needed()
            if len(values):
                self.do_print_line(fmt.plain().format(*values))
                if not skip_delta:
                    self.do_print_line(fmt.format_wsp(*deltas))
            else:
                self.do_print_line(fmt.format(*values))
        else:
            if not skip_delta:
                self.print_separator_if_needed()
                self.do_print_line(fmt.format(*deltas))


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
