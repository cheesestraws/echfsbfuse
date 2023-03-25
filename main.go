// Copyright 2020 the Go-FUSE Authors. All rights reserved.
// Use of this source code is governed by a BSD-style
// license that can be found in the LICENSE file.

// This is main program driver for a loopback filesystem that emulates
// windows semantics (no delete/rename on opened files.)
package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"path"
	"path/filepath"
	"syscall"
	"time"
	"regexp"
	"strings"

	"github.com/hanwen/go-fuse/v2/fs"
	"github.com/hanwen/go-fuse/v2/fuse"
)

var suffix *regexp.Regexp = regexp.MustCompile(",[0-9a-f]{3}$")

var underlyingPath string

type RewriteDirStream struct {
	wrapped fs.DirStream
}
var _ fs.DirStream = RewriteDirStream{}

func (r RewriteDirStream) HasNext() bool {
	return r.wrapped.HasNext()
}

func (r RewriteDirStream) Next() (fuse.DirEntry, syscall.Errno) {
	de, errno := r.wrapped.Next()
	de.Name = suffix.ReplaceAllString(de.Name, "")
	
	return de, errno
}

func (r RewriteDirStream) Close() {
	r.wrapped.Close()
}

type RewriteNode struct {
	fs.LoopbackNode
}

func newRewriteNode(rootData *fs.LoopbackRoot, _ *fs.Inode, _ string, _ *syscall.Stat_t) fs.InodeEmbedder {
	n := &RewriteNode{
		LoopbackNode: fs.LoopbackNode{
			RootData: rootData,
		},
	}
	return n
}

func (r *RewriteNode) underlyingParentPath() string {
	return filepath.Join(underlyingPath, r.Path(nil))
}

func (r *RewriteNode) realFilename(name string) string {
	// Basic file path
	filePath := filepath.Join(r.underlyingParentPath(), name)
	
	// Does the file exist under its boring old name?
	if _, err := os.Stat(filePath); !os.IsNotExist(err) {
		return name
	}
	
	// Nope.  OK.  Let's look for versions with postpended filetypes or load/exec
	// addresses.
	files, err := os.ReadDir(r.underlyingParentPath())
	if err != nil {
		log.Printf("os.ReadDir returned an error; should never happen; sod it.")
		return name;
	}
	for _, file := range files {
		n := file.Name()
		if !strings.HasPrefix(n, name) {
			continue
		}
		
		nn := suffix.ReplaceAllString(n, "")
		if nn == name {
			return n
		}
	}
		
	return name	
}

func (r *RewriteNode) Lookup(ctx context.Context, name string, out *fuse.EntryOut) (*fs.Inode, syscall.Errno) {
	fileName := r.realFilename(name)
	
	inode, err := r.LoopbackNode.Lookup(ctx, fileName, out)
	log.Printf("lookup: '%s' => '%s' : %s [%s]", name, filename, inode.Path(nil), err)

	
	return inode, err
}


func (r *RewriteNode) Getattr(ctx context.Context, f fs.FileHandle, out *fuse.AttrOut) syscall.Errno {	
	errno := r.LoopbackNode.Getattr(ctx, f, out)
	return errno
}

func (r *RewriteNode) Readdir(ctx context.Context) (fs.DirStream, syscall.Errno) {
	ds, errno := r.LoopbackNode.Readdir(ctx)
	if ds != nil {
		return RewriteDirStream{ds}, errno
	} else {
		return nil, errno
	}
}

func main() {
	log.SetFlags(log.Lmicroseconds)
	debug := flag.Bool("debug", false, "print debugging messages.")
	flag.Parse()
	if flag.NArg() < 2 {
		fmt.Printf("usage: %s MOUNTPOINT ORIGINAL\n", path.Base(os.Args[0]))
		fmt.Printf("\noptions:\n")
		flag.PrintDefaults()
		os.Exit(2)
	}

	orig := flag.Arg(1)
	rootData := &fs.LoopbackRoot{
		NewNode: newRewriteNode,
		Path:    orig,
	}

	underlyingPath = orig

	sec := time.Second
	opts := &fs.Options{
		AttrTimeout:  &sec,
		EntryTimeout: &sec,
	}
	opts.Debug = *debug
	opts.MountOptions.Options = append(opts.MountOptions.Options, "fsname="+orig)
	opts.MountOptions.Name = "echfsbfuse"
	opts.NullPermissions = true

	server, err := fs.Mount(flag.Arg(0), newRewriteNode(rootData, nil, "", nil), opts)
	if err != nil {
		log.Fatalf("Mount fail: %v\n", err)
	}
	fmt.Println("Mounted!")
	server.Wait()
}
