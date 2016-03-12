#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

"""Doc here.
"""

import argparse
from collections import namedtuple
import logging
import platform
import subprocess

import nagiosplugin


__docformat__ = 'restructuredtext en'

_log = logging.getLogger('nagiosplugin')

default_socket = '/var/run/bgpd.sock'

fields = ('Neighbor', 'AS', 'MsgRcvd', 'MsgSent', 'OutQ', 'Up_Down',
          'State_PrfRcvd')

Session = namedtuple('Session', fields)


def _popen(cmd):  # pragma: no cover
    """Try catched subprocess.popen.

    raises explicit error
    """
    try:
        proc = subprocess.Popen(cmd,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate()
        return stdout, stderr

    except OSError as e:
        message = "%s" % e
        raise nagiosplugin.CheckError(message)


class CheckBgpCtl(nagiosplugin.Resource):
    """Check bgpctl sessions plugin."""

    hostname = platform.node()

    def __init__(self, idle_list, ignore_list, socket_path=default_socket):
        self.idle_list = idle_list
        self.ignore_list = ignore_list
        self.cmd = 'bgpctl -s %s show' % socket_path

    def _get_sessions(self):
        """Runs 'bgpctl show'."""

        _log.debug("running '%s'", self.cmd)
        stdout, stderr = _popen(self.cmd.split())

        if stderr:
            message = "%s %s" % (self.hostname, stderr.splitlines()[-1])
            _log.info(message)
            raise nagiosplugin.CheckError(message)

        if stdout:
            output = stdout.splitlines()[1:]
            if output:
                return [Session(*line.rsplit(None, len(Session._fields) - 1))
                        for line in output]

    def check_session(self, session):
        """check session is up, or not in idle list if idle."""
        state = session.State_PrfRcvd

        if state.isdigit():
            result = int(state)

        return state

    def probe(self):
        """."""
        self.sessions = self._get_sessions()
        if self.sessions:
            for session in self.sessions:
                if session.Neighbor not in self.ignore_list:
                    yield nagiosplugin.Metric(session.Neighbor,
                                          self.check_session(session),
                                          min=0, context='bgpctl')


class BgpStatus(nagiosplugin.Context):
    """Context check of the BGP session"""

    def __init__(self, name, warning, critical, idle_list, fmt_metric=None,
                    result_cls=nagiosplugin.Result):
        if critical > 0:
            self.critical = int(critical)
            critical_range = "~:%s" % (self.critical,)
            self.critical_range = nagiosplugin.Range(critical_range)
        else:
            self.critical = 0
            self.critical_range = None
        if warning > critical:
            self.warning = int(warning)
            warning_range = "%s:%s" % (self.critical, self.warning)
            self.warning_range = nagiosplugin.Range(warning_range)
        else:
            self.warning = 0
            self.warning_range = None

        self.idle_list = idle_list
        self.name = name
        self.result_cls = result_cls
        self.fmt_metric = fmt_metric


    def evaluate(self, metric, resource):
        state = nagiosplugin.state.Unknown
        hint = "%s is %s, should be Established;" % (metric.name, metric.value)
        if metric.value.isdigit():
            #XXX: All of this could/should be done with a ScalarContext
            value = int(metric.value)
            if self.critical_range is not None and self.critical_range.match(value):
                state = nagiosplugin.state.Critical
                hint = "%s: prfx_rcvd %d of %d target;" % (metric.name, value,
                        self.critical)
            elif self.warning_range is not None and self.warning_range.match(value):
                state = nagiosplugin.state.Warn
                hint = "%s: prfx_rcvd %d of %d target;" % (metric.name, value,
                        self.warning)
            else:
                state = nagiosplugin.state.Ok
                hint = "%s=%s pfrx_rcvd;" % (metric.name, metric.value)

        else:
            state = nagiosplugin.state.Critical
            if metric.value == 'Idle':
                if self.idle_list is not None:
                    if metric.name in self.idle_list:
                        state = nagiosplugin.state.Ok
                        hint = "%s in idle_list" % (metric.name,)

        return self.result_cls(state, hint, metric)


class AuditSummary(nagiosplugin.Summary):
    """Status line conveying informations.
    """

    def ok(self, results):
        """Summarize OK(s)."""

        result_stats = ' '
        for result in results:
            result_stats = " %s%s" % (result, result_stats)

        return "BGP session(s) in correct state (%s)" % (result_stats,)

    def problem(self, results):
        """ Summarize Problem(s)."""

        result_stats = ' '
#        for result in results.most_significant:
        for result in results:
            if result.state is not nagiosplugin.state.Ok:
                result_stats = " %s%s" % (result, result_stats)

        return "%d Session(s): %s" % (len(results.most_significant), result_stats,)


def parse_args():  # pragma: no cover
    """Arguments parser."""
    argp = argparse.ArgumentParser(description=__doc__)
    argp.add_argument('-v', '--verbose', action='count', default=0,
                      help='increase output verbosity (use up to 3 times)')
    argp.add_argument('--idle-list', nargs='*', )
    argp.add_argument('--ignore-list', default=[None], nargs='*', )
    argp.add_argument('--socket', '-s', action='store', default=default_socket,
                      help="path to openbgpd socket (default: %(default)s)")
    argp.add_argument('--warning', '-w', type=int, default=0,
                      help="warning level for prefix received")
    argp.add_argument('--critical', '-c', type=int, default=None,
                      help="critical level for prefix received")
    return argp.parse_args()


@nagiosplugin.guarded
def main():  # pragma: no cover

    args = parse_args()
    check = nagiosplugin.Check(CheckBgpCtl(args.idle_list, args.ignore_list, args.socket),
                               BgpStatus('bgpctl', args.warning, args.critical,
                               args.idle_list),
                               AuditSummary())
    check.main(args.verbose)

if __name__ == '__main__':
    main()

# vim:set et sts=4 ts=4 tw=80:
