#!/usr/bin/env python
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
        result = 'U'
        state = session.State_PrfRcvd

        if state.isdigit():
            result = int(state)

        #XXX: does not work as expected with the new Context
        if state == 'Idle':
            if self.idle_list is not None:
                if session.Neighbor in self.idle_list:
                    result = 0

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

    def evaluate(self, metric, resource):
        if metric.value.isdigit():
            
            return self.result_cls(nagiosplugin.state.Ok,
                "%s=%s" % (metric.name, metric.value), metric)
        else:
            return self.result_cls(nagiosplugin.state.Critical,
                "%s=%s" % (metric.name, metric.value), metric)


class AuditSummary(nagiosplugin.Summary):
    """Status line conveying informations.
    """

    def ok(self, results):
        """Summarize OK(s)."""

        result_stats = ' '
        for result in results:
            result_stats = " %s%s" % (result, result_stats)

        return "bgp sessions in correct state (%s)" % (result_stats,)

    def problem(self, results):
        """ Summarize Problem(s)."""

        result_stats = ' '
        for result in results.most_significant:
            result_stats = " %s%s" % (result, result_stats)

        return "Sessions not Established: %s" % (result_stats,)


def parse_args():  # pragma: no cover
    """Arguments parser."""
    argp = argparse.ArgumentParser(description=__doc__)
    argp.add_argument('-v', '--verbose', action='count', default=0,
                      help='increase output verbosity (use up to 3 times)')
    argp.add_argument('--idle-list', nargs='*', )
    argp.add_argument('--ignore-list', nargs='*', )
    argp.add_argument('--socket', '-s', action='store', default=default_socket,
                      help="path to openbgpd socket (default: %(default)s)")
    return argp.parse_args()


@nagiosplugin.guarded
def main():  # pragma: no cover

    args = parse_args()
    check = nagiosplugin.Check(CheckBgpCtl(args.idle_list, args.ignore_list, args.socket),
                               BgpStatus('bgpctl', None),
                               AuditSummary())
    check.main(args.verbose)

if __name__ == '__main__':
    main()

# vim:set et sts=4 ts=4 tw=80:
