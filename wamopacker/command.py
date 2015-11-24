#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals
import os
from tempfile import mkdtemp
from shutil import rmtree
from jinja2 import Environment, FileSystemLoader
from json import load, dump
from .process import run_command


PRESEED_FILE_NAME = 'preseed.cfg'
PACKER_CONFIG_FILE_NAME = 'packer.json'
EXTRACTED_OVF_FILE_NAME = 'box.ovf'
REPACKAGED_VAGRANT_BOX_FILE_NAME = 'package.box'


class TempDir(object):

    def __init__(self, dir = None):
        self.path = None
        self._dir = dir

    def __enter__(self):
        if self.path:
            raise IOError('temp dir exists')

        self.path = mkdtemp(dir = self._dir)

        return self

    def __exit__(self, type, value, traceback):
        if self.path and os.path.isdir(self.path):
            rmtree(self.path)
            self.path = None


class BuilderException(Exception):
    pass


class Builder(object):

    def __init__(self, config, target_list):
        self._config = config
        self._target_list = target_list

        self._data_path = self._get_data_path()
        self._template_env = self._get_template_env(self._data_path)

    @staticmethod
    def _get_data_path():
        return os.path.join(os.path.dirname(__file__), 'data')

    @staticmethod
    def _get_template_env(data_path):
        template_path = os.path.join(data_path, 'templates')
        return Environment(loader = FileSystemLoader(template_path), trim_blocks = True)

    def build(self):
        packer_config = {
            "builders": [],
            "provisioners": [],
            "post-processors": []
        }

        temp_dir_root = self._config.temp_dir
        with TempDir(temp_dir_root) as temp_dir:
            if 'virtualbox' in self._target_list:
                self._build_virtualbox(packer_config, temp_dir)

            if 'aws' in self._target_list:
                self._build_aws(packer_config, temp_dir)

            self._add_provisioners(packer_config)

            self._add_vagrant_export(packer_config)

            self._run_packer(packer_config, temp_dir)

    def _load_json(self, name):
        file_name = os.path.join(self._data_path, name + '.json')
        with open(file_name, 'r') as file_object:
            return load(file_object)

    def _build_virtualbox(self, packer_config, temp_dir):
        if self._config.virtualbox_iso_url and self._config.virtualbox_iso_checksum:
            self._build_virtualbox_iso(packer_config, temp_dir)

        else:
            if self._config.virtualbox_vagrant_box_name and self._config.virtualbox_vagrant_box_version:
                self._build_virtualbox_vagrant_box(temp_dir)

            if self._config.virtualbox_vagrant_box_file:
                self._build_virtualbox_vagrant_box_file(temp_dir)

            if self._config.virtualbox_ovf_file:
                self._build_virtualbox_ovf_file(packer_config, temp_dir)

    def _build_virtualbox_iso(self, packer_config, temp_dir):
        packer_virtualbox_iso = self._load_json('packer_virtualbox_iso')

        for config_key, virtualbox_key in (
                ('vm_name', 'vm_name'),
                ('virtualbox_iso_url', 'iso_url'),
                ('virtualbox_iso_checksum', 'iso_checksum'),
                ('virtualbox_iso_checksum_tyoe', 'iso_checksum_type'),
                ('virtualbox_guest_os_type', 'guest_os_type'),
                ('virtualbox_disk_mb', 'disk_size'),
                ('virtualbox_user', 'ssh_username'),
                ('virtualbox_password', 'ssh_password'),
                ('virtualhox_shutdown_command', 'shutdown_command'),
                ('virtualbox_output_directory', 'output_directory'),
        ):
            if config_key in self._config:
                packer_virtualbox_iso[virtualbox_key] = getattr(self._config, config_key)

        vboxmanage_list = packer_virtualbox_iso.setdefault('vboxmanage', [])
        for vboxmanage_attr, vboxmanage_cmd in (
                ('virtualbox_memory_mb', '--memory'),
                ('virtualbox_cpus', '--cpus'),
        ):
            if vboxmanage_attr in self._config:
                vboxmanage_list.append(['modifyvm', '{{ .Name }}', vboxmanage_cmd, getattr(self._config, vboxmanage_attr)])

        self._write_virtualbox_iso_preseed(packer_virtualbox_iso, temp_dir)

        # add to the builder list
        packer_config['builders'].append(packer_virtualbox_iso)

    def _write_virtualbox_iso_preseed(self, virtualbox_config, temp_dir):
        # create the packer_http directory
        packer_http_dir = self._config.virtualbox_packer_http_dir
        packer_http_path = os.path.join(temp_dir.path, packer_http_dir)
        virtualbox_config['http_directory'] = packer_http_path
        os.mkdir(packer_http_path)

        # generate the preseed text
        preseed_template = self._template_env.get_template(PRESEED_FILE_NAME + '.j2')
        preseed_text = preseed_template.render(
            user_account = virtualbox_config['ssh_username'],
            user_password = virtualbox_config['ssh_password']
        )

        # write the preseed
        preseed_file_name = os.path.join(packer_http_path, PRESEED_FILE_NAME)
        with open(preseed_file_name, 'w') as file_object:
            file_object.write(preseed_text)

    def _build_virtualbox_ovf_file(self, packer_config, temp_dir):
        packer_virtualbox_ovf = self._load_json('packer_virtualbox_ovf')

        for config_key, virtualbox_key in (
                ('vm_name', 'vm_name'),
                ('virtualbox_user', 'ssh_username'),
                ('virtualbox_password', 'ssh_password'),
                ('virtualbox_ovf_file', 'source_path'),
                ('virtualbox_output_directory', 'output_directory'),
        ):
            if config_key in self._config:
                packer_virtualbox_ovf[virtualbox_key] = getattr(self._config, config_key)

        # add to the builder list
        packer_config['builders'].append(packer_virtualbox_ovf)

    def _build_virtualbox_vagrant_box_file(self, temp_dir):
        extract_command = "tar -xzvf '%s' -C '%s'" % (self._config.virtualbox_vagrant_box_file, temp_dir.path)
        run_command(extract_command)

        self._config.virtualbox_ovf_file = os.path.join(temp_dir.path, EXTRACTED_OVF_FILE_NAME)

    def _build_virtualbox_vagrant_box(self, temp_dir):
        extract_command = "vagrant box repackage '%s' virtualbox '%s'" % (self._config.virtualbox_vagrant_box_name, self._config.virtualbox_vagrant_box_version)
        run_command(extract_command, working_dir = temp_dir.path)

        self._config.virtualbox_vagrant_box_file = os.path.join(temp_dir.path, REPACKAGED_VAGRANT_BOX_FILE_NAME)

    def _build_aws(self, packer_config, temp_dir):
        pass

    def _add_provisioners(self, packer_config):
        if self._config.provisioning:
            if not isinstance(self._config.provisioning, list):
                raise BuilderException('Provisioning must be a list')

            value_definition_lookup = {
                'file': (
                    ('source', basestring, True),
                    ('destination', basestring, True),
                    ('direction', basestring, False),
                ),
                'shell': (
                    ('scripts', list, True),
                    ('execute_command', basestring, False),
                    ('environment_vars', list, False),
                ),
                'ansible-local': (
                    ('playbook_file', basestring, True),
                    ('playbook_dir', basestring, False),
                    ('command', basestring, False),
                    ('extra_arguments', list, False),
                ),
            }

            provisioner_list = self._config.provisioning
            for provisioner_lookup in provisioner_list:
                provisioner_type = provisioner_lookup.get('type')
                if provisioner_type in value_definition_lookup:
                    provisioner_values = self._parse_provisioner(
                        provisioner_type,
                        provisioner_lookup,
                        value_definition_lookup[provisioner_type]
                    )

                    packer_config['provisioners'].append(provisioner_values)

                else:
                    raise BuilderException("Unknown provision type: type='%s'" % provisioner_type)

    @staticmethod
    def _parse_provisioner(provisioner_type, provisioner_lookup, value_definition):
        provisioner_values = {
            'type': provisioner_type
        }

        for val_name, val_type, val_required in value_definition:
            val = provisioner_lookup.get(val_name)
            if not isinstance(val, val_type):
                if val or val_required:
                    raise BuilderException("Invalid shell provision value: name='%s' type='%s' type_expected='%s'" % (
                        val_name,
                        '' if val is None else val.__class__.__name__,
                        val_type.__name__
                    ))

            if val:
                provisioner_values[val_name] = val

        return provisioner_values

    def _add_vagrant_export(self, packer_config):
        if self._config.vagrant:
            vagrant_config = {
                'type': 'vagrant'
            }

            if self._config.vagrant_output:
                vagrant_config['output'] = self._config.vagrant_output

            if self._config.vagrant_keep_inputs:
                vagrant_config['keep_input_artifact'] = True

            packer_config['post-processors'].append(vagrant_config)

    def _run_packer(self, packer_config, temp_dir):
        packer_config_file_name = os.path.join(temp_dir.path, PACKER_CONFIG_FILE_NAME)
        self._write_packer_config(packer_config, packer_config_file_name)

        run_command('packer validate ' + packer_config_file_name)
        run_command('packer build ' + packer_config_file_name)

    def _write_packer_config(self, packer_config, file_name):
        with open(file_name, 'w') as file_object:
            dump(packer_config, file_object, indent = 4)
