# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/jammy64"

  # Forward port for Django dev server
  config.vm.network "forwarded_port", guest: 8000, host: 8000

  # Sync current project directory to VM
  config.vm.synced_folder ".", "/vagrant"

  # Install basic tools and Python 3.10
  config.vm.provision "shell", inline: <<-SHELL
    sudo apt-get update -y
    sudo apt-get install -y python3-venv python3-pip zip build-essential
    echo "alias python='python3'" >> /home/vagrant/.bash_aliases
    echo "alias pip='pip3'" >> /home/vagrant/.bash_aliases
  SHELL
end
