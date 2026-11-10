#!/bin/zsh
cd -- "${0:A:h}" || exit 1
print 'Drag the grouping RESULT directory (the one containing PESSOAS.html) here and press Enter:'
IFS= read -r directory
directory=${(Q)directory}
[[ -z "$directory" ]] && exit 1
python3 manage_face_groups.py "$directory"
print '\nPress Enter to close.'
read answer
