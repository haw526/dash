#! /usr/local/python/bin/python2.7
import gevent
from gevent import monkey
from paramiko.client import SSHClient
from paramiko.ssh_exception import AuthenticationException
from paramiko import AutoAddPolicy
import getopt
import os, sys, re
import signal


class Connection(object):
    def __init__(self, host, port, user, passwd):
        self.host = host
        self.port = port
        self.user = user
        self.passwd = passwd
        self.closed = True
        self._client = None

    def _connect(self):
        client = SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(AutoAddPolicy())
        try:

            client.connect(hostname=self.host, port=self.port, username=self.user, password=self.passwd, timeout=3)
            self.closed = False
            return client
        except AuthenticationException, e:
            return e

        except Exception, e:
            print 'No Know Exception: %s' % e

    def shell(self, **kwargs):

        if isinstance(self._client, SSHClient):
            if 'patterns' in kwargs and 'answers' in kwargs:
                patterns = kwargs['patterns']
                answers = kwargs['answers']

                def inner():
                    data = ''
                    try:
                        cmd_line = self._client.invoke_shell()
                        i = 0
                        while 1:
                            data += cmd_line.recv(1023)
                            if patterns and data.endswith(patterns[i]):
                                cmd_line.send(answers[i])
                                data = ''
                                i += 1
                            if data.endswith(']# '):
                                command = yield ''.join(data.split('\n')[-2])
                                data = ''
                                command = command + '&& echo "`hostname`: complete"\r'
                                cmd_line.send(command)
                    except Exception:
                        pass
                    finally:
                        self.closed = True
                        # self._client.close()

                f = inner()
                f.next()
                return f

    def close(self):
        if self.closed:
            print 'client connection has been closed'
        else:
            self._client.close()

    def __call__(self, *args, **kwargs):
            print 'build connection host: %s' % self.host
            self._client = self._connect()
            return self


class Dash(object):
    def __init__(self, host=None, hostfile=None):
        if hostfile:
            with open(hostfile) as f:
                self.hosts = f.readlines()
        if host:
            self.hosts = host
        if host and hostfile:
            with open('/etc/hosts') as f:
                self.hosts = [ line.split(',') for line in f ]
        self.connections = []
        self.message = MessageQ()
        self.result = {}

    def addConn(self, args):
        conn = args.get()
        if not conn.closed:
            self.connections.append(conn)
        else:
            print 'connection fail: %s' % conn

    def getResult(self, result, *args, **kwargs):
        print result.get()

    def bye(self,*args):
        for conn in self.connections:
            if not conn.closed:
                conn.close()
        sys.exit(1)

    def start(self):
        conn_tmp = []
        for host in self.hosts:
            conn = Connection(host, 22, 'root', 'aizhuo')
            g = gevent.spawn(conn)
            g.link_value(self.addConn)
            conn_tmp.append(g)
        print 'please wait, during init connection...'
        gevent.joinall(conn_tmp, timeout=3)
        signal.signal(signal.SIGINT, self.bye)
        while 1:
            command = raw_input('dash> ').strip()
            if not command:
                continue
            tmp = []
            for conn in self.connections:
                # command = self.message.getMsg()
                subash = conn.shell(patterns=None, answers=None)
                g = gevent.spawn(subash.send, command)
                g.link_value(self.getResult)
                tmp.append(g)
            gevent.joinall(tmp)


class MessageQ(object):
    def __init__(self):
        self.commands = {}

    def publish(self, command):
        self.commands.update(command)

    def getMsg(self):
        for key, value in self.commands.iteritems():
            if value == 0:
                self.commands.pop(key)
            else:
                self.commands[key] -= 1
        return self.commands.keys()


def main():
    opts, args = getopt.getopt(sys.argv[1:], 'hr:f:')
    for opt, value in opts:
        if opt in ('-h', '--help'):
            print '''usage:
                    -h  help infomation
                    -r  host1,host2   host that your want to control
                    -f  hostfile      hostfile that your want to control is list
                                      file format eg:
                                            host1
                                            host2
            '''
            sys.exit(1)
        elif opt in ('-r', '--remote'):
            hosts = value.split(',')
            Dash(hosts).start()

        elif opt in ('-f', '--file'):
            if os.path.isabs(value):
                filename = value
            else:
                filename = os.path.join(os.getcwd(), value)
            Dash(filename).start()


if __name__ == '__main__':
    main()
