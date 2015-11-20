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

        return fmt.plain(), values, values

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


def stdin_feed(sep_interval):
    while True:
        ts = time.time()
        line = sys.stdin.readline()
        if sys.version_info[0] == 2:
            line = line.decode(encoding)
        if not line:
            break
        yield line, (time.time() - ts) > sep_interval


def command_feed(cmd, interval):
    _, encoding = locale.getdefaultlocale()
    if len(cmd) == 1:
        shell = os.getenv(u'SHELL', u'/bin/sh')
        cmd = (shell, u'-c') + cmd
    while True:
        output = subprocess.check_output(cmd)
        first = True
        for line in output.splitlines():
            yield line.decode(encoding) + u'\n', first
            first = False
        time.sleep(interval)


@click.command()
@click.option(u'-t/-T', u'--timestamps/--no-timestamps', help=u'Show timestamps on all output lines')
@click.option(u'-i', u'--interval', metavar=u'SECONDS', type=click.INT,
    help=u'Interval between command runs', default=1)
@click.option(u'-f/-F', u'--flex/--no-flex', help=u'Tweak column widths for better output (default is on)', default=True)
@click.option(u'-s/-S', u'--separators/--no-separators', help=u'Show separators between chunks of output (default is on)', default=True)
@click.option(u'-c', u'--color', type=click.Choice([u'never', u'auto', u'always']), help=u'Color output', default=u'auto')
@click.option(u'-o/-O', u'--orig/--no-orig', help=u'Show original output interleaved with deltas')
@click.option(u'-z/-Z', u'--skip-zeros/--with-zeros', help=u'Skip all-zero deltas')
@click.option(u'-a/-A', u'--absolute/--relative', help=u'Show deltas from original value, not last')
@click.argument(u'cmd', nargs=-1, required=False)
def cli(timestamps, cmd, interval, flex, separators, color, orig, skip_zeros, absolute):
    if cmd:
        feed = command_feed(cmd, interval)
    else:
        feed = stdin_feed(interval * 0.8)

    if color == u'never':
        color = False
    elif color == u'always':
        color = True
    else:
        color = os.isatty(sys.stdout.fileno())

    parser = Parser(flex, absolute, color)

    def p(line, with_sep=False):
        if with_sep:
            if timestamps:
                sys.stdout.write(u'{}\n'.format(time.asctime()))
            else:
                sys.stdout.write(u'--- {}\n'.format(time.asctime()))
        if timestamps:
            sys.stdout.write(u'{}: '.format(time.asctime()))
        sys.stdout.write(line)
        sys.stdout.flush()

    try:
        print_sep = True
        for line, want_sep in feed:
            fmt, deltas, values = parser.process(line)

            all_zeros = all(d == 0 for d in deltas)
            print_sep = print_sep or want_sep
            with_sep = separators and print_sep and len(parser.formats) > 1
            if orig:
                print_sep = False
                if len(values):
                    p(fmt.plain().format(*values), with_sep=with_sep)
                    if values != deltas and (not skip_zeros or not all_zeros):
                        p(fmt.format_wsp(*deltas))
                else:
                    p(fmt.format(*values), with_sep=with_sep)
            else:
                if not skip_zeros or not all_zeros:
                    print_sep = False
                    p(fmt.format(*deltas), with_sep=with_sep)

    except KeyboardInterrupt:
        pass
    except IOError:
        return

if __name__ == u'__main__':
    cli()
