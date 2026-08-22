#!/bin/bash
# Create source-only release archives without host-specific filesystem metadata.

create_release_archive() {
  env \
    COPYFILE_DISABLE=1 \
    COPY_EXTENDED_ATTRIBUTES_DISABLE=1 \
    tar \
      --no-acls \
      --no-xattrs \
      --exclude='._*' \
      --exclude='*/._*' \
      --exclude='.DS_Store' \
      --exclude='*/.DS_Store' \
      "$@"
}
