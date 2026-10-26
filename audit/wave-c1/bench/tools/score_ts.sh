#!/bin/zsh
# usage: score_ts.sh <workspace> <hidden-test-file>  -> prints "pass fail" from hidden tests run against the workspace's src/
ws=$1; h=$2; t=$(mktemp -d); cp -R $ws/src $t/src; cp $ws/package.json $t/ 2>/dev/null || echo '{"type":"module"}' > $t/package.json; mkdir $t/test; cp $h $t/test/hidden.test.ts
(cd $t && node --test test/hidden.test.ts 2>&1 | grep -E "^ℹ (pass|fail)" | tr '\n' ' '; echo)
rm -rf $t
