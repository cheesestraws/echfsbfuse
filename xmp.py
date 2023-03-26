#!/usr/bin/env python

#    Copyright (C) 2001  Jeff Epler  <jepler@unpythonic.dhs.org>
#    Copyright (C) 2006  Csaba Henk  <csaba.henk@creo.hu>
#
#    This program can be distributed under the terms of the GNU LGPL.
#    See the file COPYING.
#

from __future__ import print_function

import os, sys
from errno import *
from stat import *
import fcntl
import re
from threading import Lock
# pull in some spaghetti to make this stuff work without fuse-py being installed
try:
    import _find_fuse_parts
except ImportError:
    pass
import fuse
from fuse import Fuse


if not hasattr(fuse, '__version__'):
    raise RuntimeError("your fuse-py doesn't know of fuse.__version__, probably it's too old.")

fuse.fuse_python_api = (0, 2)

flog = open("/tmp/flog", "w")

fuse.feature_assert('stateful_files', 'has_init')


def flag2mode(flags):
    md = {os.O_RDONLY: 'rb', os.O_WRONLY: 'wb', os.O_RDWR: 'wb+'}
    m = md[flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR)]

    if flags | os.O_APPEND:
        m = m.replace('w', 'a', 1)

    return m

def dbg(x):
	flog.write(x + "\n")
	flog.flush()

def real_path_of(path):
	# if file exists, just return it
	if os.path.exists(path):
		return path
	
	# otherwise we need the file name
	head, tail = os.path.split(path)
	if tail == "":
		return path
	
	for i in os.listdir(head):
		if i.startswith(tail):
			f = re.sub(",[0-9a-fA-F]{3}$", "", i)
			if f == tail:
				return head + "/" + i
				
	return path

def type_from_real_path(path):
	xs = re.findall(",([0-9a-fA-F]{3})$", path)
	if len(xs) == 0:
		return ""
	return xs[0]
	
def load_exec_from_real_path(path):
	xs = re.findall(",([0-9a-fA-F]{8})-([0-9a-fA-F]{8})$", path)
	if len(xs) == 0:
		return ()
	return xs[0]
	
def load_exec(path):
	p = real_path_of("." + path)
	# real load and exec addresses?
	
	dbg("real path " + p)
	
	le = load_exec_from_real_path(p)
	if le:
		return le
	
	dbg("not loadexec")
	
	# filetype?
	t = type_from_real_path(p)
	if t != "":
		# filetype!
		load = 0xfff00000
		ft = int(t, 16)
		load |= ft << 8
		exec_a = 0
		
		# timestamp!
		info = os.lstat(p)
		dbg("mtime " + ("%d" % info.st_mtime))
		
		low = (info.st_mtime & 255) * 100
		
		dbg("low")
		
		high = (info.st_mtime / 256) * 100 + (low >> 8) + 0x336e996a
		
		dbg("hi")
		
		dbg("h/l " + ("%d" % high) + " " + ("%d" % low))
		
		load |= (high >> 24)
		exec_a = (low & 0xff) | (high << 8)
		
		load_str = "%08x" % load
		exec_str = "%08x" % exec_a
		
		return load_str, exec_str

	
class Xmp(Fuse):

    def __init__(self, *args, **kw):

        Fuse.__init__(self, *args, **kw)

        self.root = '/home/cheesey/one'

    def getattr(self, path):
        return os.lstat(real_path_of("." + path))

    def readlink(self, path):
        return os.readlink(real_path_of("." + path))

    def readdir(self, path, offset):
        for e in os.listdir("." + path):
            e = re.sub(",[0-9a-fA-F]{3}$", "", e)
            yield fuse.Direntry(e)

    def unlink(self, path):
        os.unlink(real_path_of("." + path))

    def rmdir(self, path):
        os.rmdir(real_path_of("." + path))

    def symlink(self, path, path1):
        os.symlink(real_path_of(path), real_path_of("." + path1))

    def rename(self, path, path1):
        os.rename("." + path, real_path_of("." + path1))

    def link(self, path, path1):
        os.link("." + path, real_path_of("." + path1))

    def chmod(self, path, mode):
        os.chmod(real_path_of("." + path), mode)

    def chown(self, path, user, group):
        os.chown(real_path_of("." + path), user, group)

    def truncate(self, path, len):
        f = open("." + path, "a")
        f.truncate(len)
        f.close()

    def mknod(self, path, mode, dev):
        os.mknod("." + path, mode, dev)

    def mkdir(self, path, mode):
        os.mkdir(real_path_of("." + path), mode)

    def utime(self, path, times):
        os.utime(real_path_of("." + path), times)

    def access(self, path, mode):
        if not os.access(real_path_of("." + path), mode):
            return -EACCES		

#    This is how we could add stub extended attribute handlers...
#    (We can't have ones which aptly delegate requests to the underlying fs
#    because Python lacks a standard xattr interface.)
#
#    def getxattr(self, path, name, size):
#        val = name.swapcase() + '@' + path
#        if size == 0:
#            # We are asked for size of the value.
#            return len(val)
#        return val
#
#    def listxattr(self, path, size):
#        # We use the "user" namespace to please XFS utils
#        aa = ["user." + a for a in ("foo", "bar")]
#        if size == 0:
#            # We are asked for size of the attr list, ie. joint size of attrs
#            # plus null separators.
#            return len("".join(aa)) + len(aa)
#        return aa
    
    def getxattr(self, path, name, size):
    	dbg("getxattr")
    	if name == "user.econet_exec":
			dbg("getxattr/exec")
			load, exec_a = load_exec(path)
			dbg("exec " + exec_a)
			if size == 0:
				return len(exec_a)
			return exec_a
    	if name == "user.econet_load":
			load, exec_a = load_exec(path)
			dbg("load " + load)
			if size == 0:
				return len(load)
			return load
    
        val = name.swapcase() + '@' + path
        if size == 0:
            # We are asked for size of the value.
            return len(val)
        return val
    
    def listxattr(self, path, size):
        aa = ["user." + a for a in ("econet_exec", "econet_homeof", "econet_load", "econet_owner", "econet_perm")]
        if size == 0:
            # We are asked for size of the attr list, ie. joint size of attrs
            # plus null separators.
            return len("".join(aa)) + len(aa)
        return aa


    def statfs(self):
        """
        Should return an object with statvfs attributes (f_bsize, f_frsize...).
        Eg., the return value of os.statvfs() is such a thing (since py 2.2).
        If you are not reusing an existing statvfs object, start with
        fuse.StatVFS(), and define the attributes.

        To provide usable information (ie., you want sensible df(1)
        output, you are suggested to specify the following attributes:

            - f_bsize - preferred size of file blocks, in bytes
            - f_frsize - fundamental size of file blcoks, in bytes
                [if you have no idea, use the same as blocksize]
            - f_blocks - total number of blocks in the filesystem
            - f_bfree - number of free blocks
            - f_files - total number of file inodes
            - f_ffree - nunber of free file inodes
        """

        return os.statvfs(".")

    def fsinit(self):
        os.chdir(self.root)

    class XmpFile(object):

        def __init__(self, path, flags, *mode):
        	
            self.file = os.fdopen(os.open(real_path_of("." + path), flags, *mode),
                                  flag2mode(flags))
            self.fd = self.file.fileno()
            if hasattr(os, 'pread'):
                self.iolock = None
            else:
                self.iolock = Lock()

        def read(self, length, offset):
            if self.iolock:
                self.iolock.acquire()
                try:
                    self.file.seek(offset)
                    return self.file.read(length)
                finally:
                    self.iolock.release()
            else:
                return os.pread(self.fd, length, offset)

        def write(self, buf, offset):
            if self.iolock:
                self.iolock.acquire()
                try:
                    self.file.seek(offset)
                    self.file.write(buf)
                    return len(buf)
                finally:
                    self.iolock.release()
            else:
                return os.pwrite(self.fd, buf, offset)

        def release(self, flags):
            self.file.close()

        def _fflush(self):
            if 'w' in self.file.mode or 'a' in self.file.mode:
                self.file.flush()

        def fsync(self, isfsyncfile):
            self._fflush()
            if isfsyncfile and hasattr(os, 'fdatasync'):
                os.fdatasync(self.fd)
            else:
                os.fsync(self.fd)

        def flush(self):
            self._fflush()
            # cf. xmp_flush() in fusexmp_fh.c
            os.close(os.dup(self.fd))

        def fgetattr(self):
            return os.fstat(self.fd)

        def ftruncate(self, len):
            self.file.truncate(len)

        def lock(self, cmd, owner, **kw):
            # Convert fcntl-ish lock parameters to Python's weird
            # lockf(3)/flock(2) medley locking API...
            op = { fcntl.F_UNLCK : fcntl.LOCK_UN,
                   fcntl.F_RDLCK : fcntl.LOCK_SH,
                   fcntl.F_WRLCK : fcntl.LOCK_EX }[kw['l_type']]
            if cmd == fcntl.F_GETLK:
                return -EOPNOTSUPP
            elif cmd == fcntl.F_SETLK:
                if op != fcntl.LOCK_UN:
                    op |= fcntl.LOCK_NB
            elif cmd == fcntl.F_SETLKW:
                pass
            else:
                return -EINVAL

            fcntl.lockf(self.fd, op, kw['l_start'], kw['l_len'])


    def main(self, *a, **kw):

        self.file_class = self.XmpFile

        return Fuse.main(self, *a, **kw)


def main():

    usage = """
Userspace nullfs-alike: mirror the filesystem tree from some point on.

""" + Fuse.fusage

    server = Xmp(version="%prog " + fuse.__version__,
                 usage=usage,
                 dash_s_do='setsingle')

    server.parser.add_option(mountopt="root", metavar="PATH", default='/',
                             help="mirror filesystem from under PATH [default: %default]")
    server.parse(values=server, errex=1)

    try:
        if server.fuse_args.mount_expected():
            os.chdir(server.root)
    except OSError:
        print("can't enter root of underlying filesystem", file=sys.stderr)
        sys.exit(1)

    server.main()


if __name__ == '__main__':
    main()
