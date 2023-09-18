#!/bin/bash

PATH_TO_JAR=/etc/remote-iot/services/remoteiot.jar

deleteData() {
	cd
	/etc/init.d/remote-iot stop &>/dev/null &
	rm -drf /etc/remote-iot.tar.gz
	rm -drf /etc/remote-iot
	rm -drf /etc/init.d/remote-iot
}

if [ "$EUID" -ne 0 ]
then
    echo ""
    echo "Please run the install script as root or sudo"
    echo ""
    exit
fi

if [ -f $PATH_TO_JAR ]; then
	ReleaseNow="$(java -cp $PATH_TO_JAR com.remoteiot.client.version.ReleaseNow)"
	if [ "$ReleaseNow" -ge 20230508 ]; then
		if [ -z "$1" ]; then
			echo ""
			echo "Usage: curl -s -L 'https://remoteiot.com/install/uninstall.sh' | sudo bash -s 'your_setup_key'"
			echo ""
			exit 0
		fi	

		java -Xms256m -cp $PATH_TO_JAR com.remoteiot.client.DeleteDevice "$1"
		if [ $? == 0 ]; then
			deleteData
		fi
	else
		deleteData
		echo ''
		echo '*** This RemoteIoT service has been uninstalled. ***'
		echo ''
	fi
else
	echo ''
	echo '*** This RemoteIoT service is not registered or has been removed. ***'
	echo ''
fi
