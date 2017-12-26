#!/usr/bin/env python

# Copyright (c) Microsoft Corporation
# All rights reserved.
#
# MIT License
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and
# to permit persons to whom the Software is furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED *AS IS*, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING
# BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import os
import sys
import kazoo
import subprocess



def execute_shell_with_output(shell_cmd, error_msg):

    return_code = 0

    try:
        res = subprocess.check_output( shell_cmd, shell=True )

    except subprocess.CalledProcessError as err:
        print error_msg
        return_code = err.returncode
        res = err.output

    return res, return_code



def execute_shell(shell_cmd, error_msg):

    try:
        subprocess.check_call( shell_cmd, shell=True )

    except subprocess.CalledProcessError:
        print error_msg
        sys.exit(1)



if __name__ == "__main__":

    # Will be filled when namenode bootstraping
    host = {{ host_config['ip'] }}
    isBootstrapping = False
    hasActiveNameNode = False
    isNewNameNode = os.listdir("/var/lib/hdfs/name") == []

    # Will be filled when namenode bootstraping
    zookeeper_quorum={%- for host in cluster_config if 'zkid' in cluster_config[ host ] -%}
{{cluster_config[ host ]['ip']}}:2181{% if not loop.last %},{% endif %}
{%- endfor -%}
    zk = kazoo.client.KazooClient(hosts=zookeeper_quorum)
    zk.start()

    lock = zk.lock("/namenodelock", host)
    with lock:

        ret, ret_code = execute_shell_with_output(
            "hdfs getconf -namenodes",
            "Failed to run < run hdfs getconf -namenodes failed >"
        )
        if ret_code != 0:
            print ret
            raise Exception("HDFS config command did not run successfully, error code: {0}".format(ret_code))
        print "========== NameNode: {0}".format(ret)

        ret, ret_code = execute_shell_with_output(
            "hdfs getconf -confKey dfs.ha.namenodes.paicluster",
            "Failed to run < hdfs getconf -confKey dfs.ha.namenodes.paicluster >"
        )
        if ret_code != 0:
            print ret
            raise Exception("HDFS config command did not run successfully, error code: {0}".format(ret_code))
        print "========== NameNode aliases: {0}".format(ret)

        for nn in ret.split(","):

            print "========== NameNode {0} state:".format(nn)

            ret, ret_code = execute_shell_with_output(
                "hdfs getconf -confKey dfs.namenode.rpc-address.paicluster.{0}".format(nn),
                "Failed to run < hdfs getconf -confKey dfs.namenode.rpc-address.paicluster.{0} >".format(nn)
            )
            if ret_code != 0:
                print ret
                raise Exception("HDFS config command did not run successfully, error code: %d".format(ret_code))
            hostString = ret

            ret, ret_code = execute_shell_with_output(
                "hdfs haadmin -getServiceState {0}".format(nn),
                "Failed to run < hdfs haadmin -getServiceState {0} >".format(nn),
            )
            if ret_code == 0:
                print ret
                if host in hostString:
                    raise Exception("Current node is already active in the Hadoop cluster")
                else:
                    hasActiveNameNode = True
            else:
                print ret

        print "\n================================================================\n"

        hadoop_ha_node = zk.exists(path="/hadoop-ha")

        if hadoop_ha_node == None:

            print "========== Hadoop HA ZK Failover controller znode does not exist"
            isBootstrapping = True
            ret, ret_code = execute_shell_with_output(
                "hdfs zkfc -formatZK -nonInteractive",
                "Failed to run < hdfs zkfc -formatZK -nonInteractive >"
            )
            print ret

        else:

            print "========== Hadoop HA ZK Failover controller znode already exists"

        if isBootstrapping and isNewNameNode:

            print "============== Bootstrapping new name node"
            ret, ret_code = execute_shell_with_output(
                "hdfs zkfc -formatZK -nonInteractive",
                "Failed to run < hdfs zkfc -formatZK -nonInteractive >"
            )
            print ret

        elif isBootstrapping:

            raise Exception("Bootstrapping, but there is already some data on the node")

        elif isNewNameNode:

            print "============== Adding new standby name node to an existing Hadoop cluster"
            if not hasActiveNameNode:
                raise Exception("Adding a name node to existing Hadoop cluster without any name nodes already active. It is a benign race if it happens during bootstrapping.")
            ret, ret_code = execute_shell_with_output(
                "hdfs namenode -bootstrapStandby -nonInteractive",
                "Failed to run < hdfs namenode -bootstrapStandby -nonInteractive >"
            )
        else:
            print "============== Starting existing name node"


print "============== Finished initialize script"
