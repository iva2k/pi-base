#!/bin/bash
#
# ---------------------------------------------------------------------
# RemoteIoT installtion script.
# ---------------------------------------------------------------------

DOWNLOAD_URL='https://download.remoteiot.com'
MAIN_URL='https://remoteiot.com'
CC_URL='http://remoteiot.cc'
SERVER_URL="$DOWNLOAD_URL"
PATH_TO_LOG=/tmp/remoteiot.log
PATH_TO_JAR=/etc/remote-iot/services/remoteiot.jar
PATH_TO_CHK=/etc/remote-iot/services/remoteiotchk.sh
PROGRAM_CHECK=remoteiotchk.sh
PROGRAM_JAR=remoteiot.jar

getSystemType() {
    which apt-get >/dev/null 2>/dev/null
    if [ $? == 0 ]; then
        return 1;
    fi
    which yum >/dev/null 2>/dev/null
    if [ $? == 0 ]; then
        return 2;
    fi
    which opkg >/dev/null 2>/dev/null
    if [ $? == 0 ]; then
        return 3;
    fi
}

installApp() {
    if which $1 >/dev/null 2>/dev/null; then
        return;
    fi

    getSystemType
    sys=$?    
    if [ $sys == 1 ]; then
        apt-get -y install $1
    elif [ $sys == 2 ]; then
        yum -y install $1
    elif [ $sys == 3 ]; then
        opkg update >/dev/null 2>/dev/null
        opkg install $1
    fi
}

findProgram() {
    getSystemType
    sys=$?
    if [[ $sys == 1 || $sys == 2 ]]; then
        sn=`ps -ef | grep "$1" | grep -v grep |awk '{print $2}'`
    else
        sn=`ps | grep "$1" | grep -v grep |awk '{print $1}'`  
    fi
    if [ "${sn}" != "" ]    
    then
        return 1
    else
        return 0
    fi
}

stopProgram() {
    getSystemType
    sys=$?    
    if [[ $sys == 1 || $sys == 2 ]]; then
        sn=`ps -ef | grep "$1" | grep -v grep |awk '{print $2}'` 
    else
        sn=`ps | grep "$1" | grep -v grep |awk '{print $1}'`  
    fi
    if [ "${sn}" != "" ]    
    then
        for i in `echo "${sn}" | sed 's/,/\n/g'`
        do  
            kill -9 "${i}"
        done
    fi
}

checkJava() {
    _java=''
    if which java >/dev/null 2>/dev/null; then
        _java=java
    elif [[ -n "$JAVA_HOME" ]] && [[ -x "$JAVA_HOME/bin/java" ]];  then
        _java="$JAVA_HOME/bin/java"
    fi
    if [[ "$_java" ]]; then
        version=$("$_java" -version 2>&1 | awk -F '"' '/version/ {print $2}')
        if [ -z "$version" ]; then
            _java=''
        else
            version1=$(echo "$version" | awk -F'.' '{print $1}')
            version2=$(echo "$version" | awk -F'.' '{print $2}')
            if [[ "$version1" -gt "1" && "$version1" -lt "8" ]] || [[ "$version1" -eq "1" && "$version2" -lt "8" ]]; then
                _java=''
            fi
        fi
    fi
}

installJava() {
    getSystemType
    sys=$?

    checkJava
    if [ -z "$_java" ]; then
        if [ $sys == 1 ]; then
            apt-get -y install openjdk-11-jre-headless
        elif [ $sys == 2 ]; then
            yum -y install java-1.8.0-openjdk*
        elif [ $sys == 3 ]; then
            curl -L "$MAIN_URL/install/install-openjdk-openwrt.sh" | bash
            export JAVA_HOME=/usr/lib/java
            export PATH=$PATH:$JAVA_HOME/bin
        fi
    fi

    checkJava
    if [ -z "$_java" ]; then
        if [ ! -d '/usr/lib/jvm' ]; then
            mkdir /usr/lib/jvm
        fi
        cd /usr/lib/jvm
        platform=$(uname -m)
        javaf=''
        if [ `echo $platform | grep -c "x86"` -gt 0 ]; then
            if [ $(getconf LONG_BIT) == '64' ]; then
                javaf=jdk-8u202-linux-x64.tar.gz
            else
                javaf=jdk-8u202-linux-i586.tar.gz
            fi
        else
            if [ $(getconf LONG_BIT) == '64' ]; then
                javaf=jdk-8u202-linux-arm64-vfp-hflt.tar.gz
            else
                javaf=jdk-8u202-linux-arm32-vfp-hflt.tar.gz
            fi
        fi

        rm -f "$javaf"
        getDownloadUrl
        wget "$SERVER_URL/install/$javaf" -O "$javaf"
        if [ $? == 0 ]; then
            tar -xzf "$javaf"
            if [ $? == 0 ] && [ -f '/usr/lib/jvm/jdk1.8.0_202/bin/java' ]; then
                rm -f "$javaf"
                update-alternatives --install /usr/bin/java java /usr/lib/jvm/jdk1.8.0_202/bin/java 1
                update-alternatives --set java /usr/lib/jvm/jdk1.8.0_202/bin/java
            else
                echo ""
                echo "*** Can't download the installation file. Please try again later ***"
                echo ""
                exit
            fi
        else 
            echo ""
            echo "*** Connection timed out. Please try again later ***"
            echo ""
            exit
        fi
    fi

    PATH_TO_postinst=/var/lib/dpkg/info/ca-certificates-java.postinst
    if [ -f $PATH_TO_postinst ]; then
       $PATH_TO_postinst configure > /dev/null 2>&1
    fi
    java -version
    if [ $? != 0 ]; then
        echo ""
        echo "*** Can't find Java VM ***"
        echo ""
    fi
}

getDownloadUrl() {
    curl -s -o "/dev/null" "$DOWNLOAD_URL"
    if [ $? == 0 ] ; then
        SERVER_URL="$DOWNLOAD_URL"
        return
    fi
    curl -s -o "/dev/null" "$MAIN_URL"
    if [ $? == 0 ] ; then
        SERVER_URL="$MAIN_URL"
        return
    fi
    curl -s -o "/dev/null" "$CC_URL"
    if [ $? == 0 ] ; then
        SERVER_URL="$CC_URL"
        return
    fi
    SERVER_URL="$MAIN_URL"
}

checkSum() {
    retval="false"
    local_file="$1"
    getDownloadUrl
    remote_file="$SERVER_URL/install/$2"
    if [ -f $local_file ]; then
        md5sum_exe="$(which md5sum)"
        if [ "$md5sum_exe" == "" ]; then
            retval="true"
        else
            server_chksum="$(curl -s -L $remote_file)"
            local_chksum="$(md5sum -b $local_file | cut -d " " -f1)"
            if [ "$server_chksum" == "$local_chksum" ]; then
                retval="true"
            fi
        fi
    fi
    echo "$retval"
}

downloadFile() {
    retval="false"
    installApp 'curl'
    installApp 'wget'
    
    getDownloadUrl
    wget "$SERVER_URL/install/$1" -O "/etc/$1"
    if [ $? == 0 ]; then
        retval=$(checkSum "/etc/$1" "$2")
    fi
    echo "$retval"
}

addCronJob() {
    if [[ $(crontab -l | egrep -v "^(#|$)" | grep -q 'iot.com/install/upgrade'; echo $?) == 1 ]]
    then
        minute="$((RANDOM % 60))"
        hour="$((RANDOM % 4))"
        command="* * * curl -s -L $MAIN_URL/install/upgrade.sh | bash"
        scripts="${minute} ${hour} ${command}"
        echo "$(crontab -l 2>/dev/null; echo "${scripts}")" | crontab -
    fi
}

installProgram() {
    getSystemType
    sys=$?
    installApp 'curl'
    installApp 'wget'
    
    if [ $sys == 3 ]; then
        opkg install curl wget libnss libstdcpp bash ca-bundle libustream-openssl ca-certificates;
    fi
    installJava

    old_pwd=$(pwd)
    retval=$(downloadFile 'remote-iot.tar.gz' 'md5sum.txt')
    if [ "$retval" == "true" ]; then
        cd /etc/
        tar -xzf remote-iot.tar.gz
        if [ $? == 0 ]; then
            rm -rf /etc/init.d/remote-iot
            mkdir -p /etc/init.d/

            if [ $sys == 1 ]; then
                cp /etc/remote-iot/services/remote-iot /etc/init.d/
                chmod a+x /etc/init.d/remote-iot
                chmod a+x /etc/remote-iot/services/*.sh
                /usr/sbin/update-rc.d remote-iot defaults 98
            elif [ $sys == 2 ]; then
                cp /etc/remote-iot/services/remote-iot /etc/init.d/
                chmod a+x /etc/init.d/remote-iot
                chmod a+x /etc/remote-iot/services/*.sh
                chkconfig --add remote-iot
                chkconfig remote-iot on
            elif [ $sys == 3 ]; then
                cp /etc/remote-iot/services/remote-iot-openwrt /etc/init.d/remote-iot
                chmod a+x /etc/init.d/remote-iot
                chmod a+x /etc/remote-iot/services/*.sh
                /etc/init.d/remote-iot enable
            fi
            rm -f remote-iot.tar.gz
            cd "${old_pwd}"
            return 0
        else
            echo "Failed to download file. Please try again later."
            rm -f remote-iot.tar.gz
        fi
    else
        echo "Failed to download file. Please try again later."
    fi
    cd "${old_pwd}"
    return 1
}

setupApp() {
    rm -rf /etc/remote-iot/configure
    rm -rf /etc/remote-iot/db

    java -Xms256m -cp $PATH_TO_JAR com.remoteiot.client.RegisterDevice "$1" "$2" "$3" "$4" "$5"
    ret=$?
    if [ $ret == 0 ]; then
        addCronJob
        /etc/init.d/remote-iot restart &>/dev/null &
    elif [ $ret -gt 1 ]; then
        printf '\n*** OutOfMemory: please reboot the device ***\n\n'
    fi
}

stopCheck() {
    stopProgram "$PROGRAM_CHECK"
}

startCheck() {
    stopCheck
    sleep 1
    $PATH_TO_CHK >>$PATH_TO_LOG 2>&1 &
}

stopApp() { 
    stopProgram "$PROGRAM_JAR"
}

startApp() {
    stopApp
    sleep 1
    java -jar $PATH_TO_JAR >>$PATH_TO_LOG 2>&1 &
}

# ---------------------------------------------------------------------

if [ "$EUID" -ne 0 ]
then
    echo ""
    echo "Please run the install script as root or sudo"
    echo ""
    exit
fi

if [ -z "$1" ]; then
    echo ""
    echo "Usage: curl -s -L 'https://remoteiot.com/install/install.sh' | sudo bash -s 'your_setup_key' 'device_name' 'device_note'"
    echo ""
    exit 0
fi

installProgram
if [ $? == 0 ]; then
    setupApp "$1" "$2" "$3" "$4" "$5"
fi



