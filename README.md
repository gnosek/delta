# Delta -- a quick tool to see changing numeric values in the shell

## Motivation

While debugging various issues you often get relevant data as always-increasing counters,
like the Linux VM page fault stats:

    $ for i in `seq 1 5` ; do grep fault /proc/vmstat ; sleep 1 ; done
    pgfault 78258716080
    pgmajfault 3202798
    thp_fault_alloc 0
    thp_fault_fallback 0
    pgfault 78258733001
    pgmajfault 3202799
    thp_fault_alloc 0
    thp_fault_fallback 0
    pgfault 78258754872
    pgmajfault 3202799
    thp_fault_alloc 0
    thp_fault_fallback 0
    pgfault 78258833733
    pgmajfault 3202799
    thp_fault_alloc 0
    thp_fault_fallback 0
    pgfault 78258865018
    pgmajfault 3202799
    thp_fault_alloc 0
    thp_fault_fallback 0

Now, quick: how many page faults per second were there? Did any major faults happen?

Let's say 20k-ish. Or let's see exactly:

    $ timeout 5 delta grep fault /proc/vmstat
    pgfault 78262968904
    pgmajfault 3202834
    thp_fault_alloc  0
    thp_fault_fallback  0
    --- Thu Nov 19 18:24:00 2015
    pgfault      +33040
    pgmajfault      +0
    thp_fault_alloc +0
    thp_fault_fallback +0
    --- Thu Nov 19 18:24:01 2015
    pgfault      +27092
    pgmajfault      +0
    thp_fault_alloc +0
    thp_fault_fallback +0
    --- Thu Nov 19 18:24:02 2015
    pgfault       +7653
    pgmajfault      +0
    thp_fault_alloc +0
    thp_fault_fallback +0
    --- Thu Nov 19 18:24:03 2015
    pgfault      +37106
    pgmajfault      +0
    thp_fault_alloc +0
    thp_fault_fallback +0

`delta` works on all kinds of file formats with ints or floats (except scientific notation) and does its best
to autodetect the number format for pretty output.

## Demo

[![asciicast](https://asciinema.org/a/3q1gjalxs33p2rhvvqz4ljzaf.png)](https://asciinema.org/a/3q1gjalxs33p2rhvvqz4ljzaf)

## Installation

    pip install git+https://github.com/gnosek/delta
