#!/usr/bin/python3
# Clones SVN repos using GIT SVN.
# 1. Check if the repos are accessable
# 2. Clone accessable repos, retry after 2,5s delay if clone fails (this is due to frequent connection issues)

import sys, string, os, time, subprocess

server = "https://svn.idneo.com/svn/"

repos = ['XXX_MCL32_XX_S32K1x_MCAL',
        'XXX_MCL32_XX_S32K3xx_MCAL',
        '24X_VIBEX_N2',
        'SGS_PDLCX_N2',
        '015_SCU16_N2']

tested_repos = []

os.chdir("/mnt/c/git")

for i in range(len(repos)):
    print("repo: " + repos[i] + " at revision ", end = '')
    status = subprocess.Popen(["svn", "info", server + repos[i]], stdout=subprocess.PIPE)
    output=status.communicate();
    retcode=status.returncode

    if retcode:
        print("something went wrong...")
    else:
        tested_repos.append(repos[i])
        print(output)

print("These repos can be reached: ")
print(tested_repos)


error_counter = 255

for i in range(len(tested_repos)):
    path =  server + tested_repos[i]
    command = "git svn clone -s -r `svn info " + path + " | grep Revision | cut -d' ' -f2` " + path + " -T trunk -b branches -t tags"
    print(command)
    while (os.system(command)) or error_counter:
        error_counter = error_counter - 1
        print("retrying.." + tested_repos[i])
        time.sleep(2.5)	
