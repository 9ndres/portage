# elog/messages.py - elog core functions
# Copyright 2006-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

import portage

portage.proxy.lazyimport.lazyimport(
    globals(),
    "portage.output:colorize",
    "portage.util:writemsg",
)

from portage.const import EBUILD_PHASES
from portage.localization import _
from portage import os
from portage import _encodings
from portage import _unicode_encode
from portage import _unicode_decode

import io
import sys

_log_levels = frozenset(
    [
        "ERROR",
        "INFO",
        "LOG",
        "QA",
        "WARN",
    ]
)


def collect_ebuild_messages(path):
    """Collect elog messages generated by the bash logging function stored
    at 'path'.
    """
    mylogfiles = None
    try:
        mylogfiles = os.listdir(path)
    except OSError:
        pass
    # shortcut for packages without any messages
    if not mylogfiles:
        return {}
    # exploit listdir() file order so we process log entries in chronological order
    mylogfiles.reverse()
    logentries = {}
    for msgfunction in mylogfiles:
        filename = os.path.join(path, msgfunction)
        if msgfunction not in EBUILD_PHASES:
            writemsg(
                _("!!! can't process invalid log file: %s\n") % filename, noiselevel=-1
            )
            continue
        if not msgfunction in logentries:
            logentries[msgfunction] = []
        lastmsgtype = None
        msgcontent = []
        f = io.open(
            _unicode_encode(filename, encoding=_encodings["fs"], errors="strict"),
            mode="r",
            encoding=_encodings["repo.content"],
            errors="replace",
        )
        # Use split('\n') since normal line iteration or readlines() will
        # split on \r characters as shown in bug #390833.
        for l in f.read().split("\n"):
            if not l:
                continue
            try:
                msgtype, msg = l.split(" ", 1)
                if msgtype not in _log_levels:
                    raise ValueError(msgtype)
            except ValueError:
                writemsg(
                    _("!!! malformed entry in " "log file: '%s': %s\n") % (filename, l),
                    noiselevel=-1,
                )
                continue

            if lastmsgtype is None:
                lastmsgtype = msgtype

            if msgtype == lastmsgtype:
                msgcontent.append(msg)
            else:
                if msgcontent:
                    logentries[msgfunction].append((lastmsgtype, msgcontent))
                msgcontent = [msg]
            lastmsgtype = msgtype
        f.close()
        if msgcontent:
            logentries[msgfunction].append((lastmsgtype, msgcontent))

    # clean logfiles to avoid repetitions
    for f in mylogfiles:
        try:
            os.unlink(os.path.join(path, f))
        except OSError:
            pass
    return logentries


_msgbuffer = {}


def _elog_base(level, msg, phase="other", key=None, color=None, out=None):
    """Backend for the other messaging functions, should not be called
    directly.
    """

    # TODO: Have callers pass in a more unique 'key' parameter than a plain
    # cpv, in order to ensure that messages are properly grouped together
    # for a given package instance, and also to ensure that each elog module's
    # process() function is only called once for each unique package. This is
    # needed not only when building packages in parallel, but also to preserve
    # continuity in messages when a package is simply updated, since we don't
    # want the elog_process() call from the uninstall of the old version to
    # cause discontinuity in the elog messages of the new one being installed.

    global _msgbuffer

    if out is None:
        out = sys.stdout

    if color is None:
        color = "INFO"

    msg = _unicode_decode(msg, encoding=_encodings["content"], errors="replace")

    formatted_msg = colorize(color, " * ") + msg + "\n"

    # avoid potential UnicodeEncodeError
    if out in (sys.stdout, sys.stderr):
        formatted_msg = _unicode_encode(
            formatted_msg, encoding=_encodings["stdio"], errors="backslashreplace"
        )
        out = out.buffer

    out.write(formatted_msg)

    if key not in _msgbuffer:
        _msgbuffer[key] = {}
    if phase not in _msgbuffer[key]:
        _msgbuffer[key][phase] = []
    _msgbuffer[key][phase].append((level, msg))

    # raise NotImplementedError()


def collect_messages(key=None, phasefilter=None):
    global _msgbuffer

    if key is None:
        rValue = _msgbuffer
        _reset_buffer()
    else:
        rValue = {}
        if key in _msgbuffer:
            if phasefilter is None:
                rValue[key] = _msgbuffer.pop(key)
            else:
                rValue[key] = {}
                for phase in phasefilter:
                    try:
                        rValue[key][phase] = _msgbuffer[key].pop(phase)
                    except KeyError:
                        pass
                if not _msgbuffer[key]:
                    del _msgbuffer[key]
    return rValue


def _reset_buffer():
    """Reset the internal message buffer when it has been processed,
    should not be called directly.
    """
    global _msgbuffer

    _msgbuffer = {}


# creating and exporting the actual messaging functions
_functions = {
    "einfo": ("INFO", "INFO"),
    "elog": ("LOG", "LOG"),
    "ewarn": ("WARN", "WARN"),
    "eqawarn": ("QA", "QAWARN"),
    "eerror": ("ERROR", "ERR"),
}


class _make_msgfunction:
    __slots__ = ("_color", "_level")

    def __init__(self, level, color):
        self._level = level
        self._color = color

    def __call__(self, msg, phase="other", key=None, out=None):
        """
        Display and log a message assigned to the given key/cpv.
        """
        _elog_base(self._level, msg, phase=phase, key=key, color=self._color, out=out)


for f in _functions:
    setattr(
        sys.modules[__name__], f, _make_msgfunction(_functions[f][0], _functions[f][1])
    )
del f, _functions
