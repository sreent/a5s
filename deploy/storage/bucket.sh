#!/bin/sh
# The bucket for the ledger's copies, with object lock, the way assurance would
# set it up in an account the team that runs a5s can't administer.
awslocal s3api create-bucket --bucket a5s-ledger --object-lock-enabled-for-bucket
