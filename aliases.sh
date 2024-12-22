#Aliases 

alias ..='cd ..'
alias ...='cd ../../../'
alias ....='cd ../../../../'
alias .....='cd ../../../../'
alias .4='cd ../../../../'
alias .5='cd ../../../../..'
alias c='clear'
alias ll='ls -alh'
# ls sort by size
# alias lt='ls --human-readable --size -1 -S --classify' # Linux
alias lt='du -sh * | sort -h' 
# count files recursivly
alias count='find . -type f | wc -l'
# copy with progress bar
alias cpv='rsync -ah --info=progress2'
#cg takes you to the top of your Git project, no matter how deep into its directory structure you have descended. 
alias cg='cd `git rev-parse --show-toplevel`'
alias top='atop'
alias new='ls -lth | head -15'
alias du='du -h'
alias df='df -h'
alias sudo='sudo -E'
alias grep='grep --color=auto -i'
alias egrep='egrep --color=auto'
alias fgrep='fgrep --color=auto'
alias sha1='openssl sha1'
alias diff='colordiff'
alias h='history'
alias j='jobs -l'
#Show open ports
alias ports='sudo lsof -i -P | grep LISTEN | grep :$PORT'
alias myip='ifconfig | grep "inet " | grep -Fv 127.0.0.1 | awk "{print $2}"'
alias extip='dig -4 TXT +short o-o.myaddr.l.google.com @ns1.google.com'