#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function, unicode_literals
import pytest
from wamopacker.config import (
    Config, ConfigValue,
    ConfigException, ConfigLoadException,
    CONFIG_DEFAULTS, ENV_VAR_PREFIX
)
import logging
import os
from tempfile import mkdtemp
from shutil import rmtree
from yaml import safe_dump


log = logging.getLogger('wamopacker.test_config')

TEST_VAR_NAME = 'TEST_ENV_VAR'
TEST_VAR_KEY = ENV_VAR_PREFIX + TEST_VAR_NAME
TEST_VAR_VALUE = 'meh'
YAML_CONFIG_FILE_NAME = 'config.yml'
YAML_LOOKUP_FILE_NAME = 'lookup.yml'
YAML_FILE_DATA = {
    YAML_CONFIG_FILE_NAME: {
        'fizz': 'abc',
        'buzz': 'def'
    },
    YAML_LOOKUP_FILE_NAME: {
        'abc': 'easy as',
        'def': '123'
    }
}
YAML_BAD_STRING_LIST = (
    "",
    "a=b",
    "foo: bar: bam",
    """---
string
""",
    """---
- list
""",
    """---
123
""",
)
MISSING_FILE_NAME = '/file/does/not/exist.yml'


# Config default fixtures

@pytest.fixture()
def no_env_vars():
    if TEST_VAR_KEY in os.environ:
        del(os.environ[TEST_VAR_KEY])


@pytest.fixture()
def with_env_vars():
    os.environ[TEST_VAR_KEY] = TEST_VAR_VALUE


@pytest.fixture()
def config_no_env_vars(no_env_vars):
    return Config()


@pytest.fixture()
def config_with_env_vars(with_env_vars):
    return Config()


@pytest.fixture()
def config_with_override_list(no_env_vars):
    override_list = ['{}={}'.format(TEST_VAR_NAME, TEST_VAR_VALUE)]
    return Config(override_list = override_list)


# ConfigValue

@pytest.fixture()
def config_value_config(with_env_vars):
    config_str = """---
foo: 123
bar: '456'
empty: ''
"""
    return Config(config_string = config_str)


def config_values_ids(fixture_value):
    return "'{}' == '{}'".format(*fixture_value)


@pytest.mark.parametrize(
    'config_val_str,expected',
    (
        ('', ''),
        (' ', ''),
        ('  ', ''),
        ('test', 'test'),
        (' test', 'test'),
        ('  test', 'test'),
        ('test ', 'test'),
        ('test  ', 'test'),
        (' test ', 'test'),
        ('  test  ', 'test'),
        ('((foo))', '123'),
        ('(( foo))', '123'),
        ('((foo ))', '123'),
        ('(( foo ))', '123'),
        (' (( foo ))', '123'),
        ('(( foo )) ', '123'),
        ('(( foo ))(( bar ))', '123456'),
        ('test ((foo))', 'test 123'),
        (' test ((foo))', 'test 123'),
        ('test ((foo)) ', 'test 123'),
        ('test  ((foo)) ', 'test  123'),
        ('((foo)) test', '123 test'),
        ('((foo)) test ', '123 test'),
        (' ((foo)) test', '123 test'),
        ('((foo))  test', '123  test'),
        ('(( default | foo | bar ))', 'foo'),
        ('(( default || bar ))', 'bar'),
        ('(( default | | bar ))', 'bar'),
        ('(( default | (( foo )) | bar ))', '123'),
        ('(( default | (( empty )) | bar ))', 'bar'),
        ('(( env | {} ))'.format(TEST_VAR_KEY), TEST_VAR_VALUE),
        ('(( lookup_optional | {} | foo ))'.format(MISSING_FILE_NAME), 'foo'),
        ('(( lookup_optional | {} | (( foo )) ))'.format(MISSING_FILE_NAME), '123'),
    ),
    ids = config_values_ids
)
def test_config_values(config_value_config, config_val_str, expected):
    config_value = ConfigValue(config_value_config, config_val_str)
    assert config_value.evaluate() == expected


@pytest.mark.parametrize(
    'config_val_str',
    (
        '((',
        ' ((',
        '  ((',
        '(( ',
        '((  ',
        ' (( ',
        '  ((  ',
        '))',
        ' ))',
        '  ))',
        ')) ',
        '))  ',
        ' )) ',
        '  ))  ',
        '(( undefined ))',
        '(((( foo ))))',
        '(( | ))',
        '(( undefined | ))',
        '(( env | ))',
        '(( env | UNDEFINED_ENV_VAR ))',
        '(( uuid | ))',
        '(( lookup ))',
        '(( lookup | {} ))'.format(MISSING_FILE_NAME),
        '(( lookup | {} | test ))'.format(MISSING_FILE_NAME),
    )
)
def test_config_values_bad(config_value_config, config_val_str):
    config_value = ConfigValue(config_value_config, config_val_str)
    with pytest.raises(ConfigException):
        config_value.evaluate()


# Config attributes and lookups

def test_config_contains_defaults(config_no_env_vars):
    for key, val in CONFIG_DEFAULTS.iteritems():
        assert config_no_env_vars.expand_parameters(val) == getattr(config_no_env_vars, key)


def test_config_reads_env_vars(config_no_env_vars, config_with_env_vars):
    assert TEST_VAR_NAME not in config_no_env_vars

    assert getattr(config_with_env_vars, TEST_VAR_NAME) == TEST_VAR_VALUE
    assert TEST_VAR_NAME in config_with_env_vars


def test_config_reads_override_list(config_no_env_vars, config_with_override_list):
    assert TEST_VAR_NAME not in config_no_env_vars

    assert getattr(config_with_override_list, TEST_VAR_NAME) == TEST_VAR_VALUE
    assert TEST_VAR_NAME in config_with_override_list


def test_config_can_set_attribute(config_no_env_vars):
    key, val = 'foo', 'bar'
    assert key not in config_no_env_vars
    setattr(config_no_env_vars, key, val)
    assert key in config_no_env_vars
    assert getattr(config_no_env_vars, key) == val


def test_config_can_delete_attribute(config_no_env_vars):
    key, val = 'foo', 'bar'
    setattr(config_no_env_vars, key, val)
    assert key in config_no_env_vars
    assert getattr(config_no_env_vars, key) == val
    delattr(config_no_env_vars, key)
    assert key not in config_no_env_vars


def test_config_set_none_deletes_attribute(config_no_env_vars):
    key, val = 'foo', 'bar'
    setattr(config_no_env_vars, key, val)
    assert key in config_no_env_vars
    assert getattr(config_no_env_vars, key) == val
    setattr(config_no_env_vars, key, None)
    assert key not in config_no_env_vars


def test_config_uuid(config_no_env_vars):
    config_value_a1 = ConfigValue(config_no_env_vars, '(( uuid | a ))')
    config_value_a2 = ConfigValue(config_no_env_vars, '(( uuid |  a  ))')
    config_value_b = ConfigValue(config_no_env_vars, '(( uuid | b ))')

    assert config_value_a1.evaluate()
    assert config_value_b.evaluate()
    assert config_value_a1.evaluate() == config_value_a2.evaluate()
    assert config_value_a1.evaluate() != config_value_b.evaluate()


def test_config_env_var(config_with_env_vars):
    config_value = ConfigValue(config_with_env_vars, '(( env | {} ))'.format(TEST_VAR_KEY))
    assert config_value.evaluate() == TEST_VAR_VALUE


def test_config_env_var_missing(config_no_env_vars):
    config_value = ConfigValue(config_no_env_vars, '(( env | {} ))'.format(TEST_VAR_KEY))
    with pytest.raises(ConfigException):
        config_value.evaluate()


def test_config_env_var_default(config_with_env_vars):
    default_val = 'default'
    config_value = ConfigValue(config_with_env_vars, '(( env | {} | {} ))'.format(TEST_VAR_KEY, default_val))
    assert config_value.evaluate() == TEST_VAR_VALUE


def test_config_env_var_missing_default(config_no_env_vars):
    default_val = 'default'
    config_value = ConfigValue(config_no_env_vars, '(( env | {} | {} ))'.format(TEST_VAR_KEY, default_val))
    assert config_value.evaluate() == default_val


# Config from file

@pytest.fixture()
def temp_dir(request):
    temp_dir_name = mkdtemp(prefix = 'wamopacker_pytest')
    log.info('created temp dir: {}'.format(temp_dir_name))

    current_dir = os.getcwd()

    def remove_temp_dir():
        if temp_dir_name:
            log.info('removing temp dir: {}'.format(temp_dir_name))
            rmtree(temp_dir_name)

        os.chdir(current_dir)

    request.addfinalizer(remove_temp_dir)

    return temp_dir_name


@pytest.fixture()
def config_with_files(temp_dir):
    for file_name, file_data in YAML_FILE_DATA.iteritems():
        file_name_full = os.path.join(temp_dir, file_name)
        with open(file_name_full, 'w') as file_object:
            safe_dump(file_data, file_object)

    os.chdir(temp_dir)

    config_file_name_full = os.path.join(temp_dir, YAML_CONFIG_FILE_NAME)
    return Config(config_file_name = config_file_name_full)


def test_config_files(config_with_files):
    for key, value in YAML_FILE_DATA[YAML_CONFIG_FILE_NAME].iteritems():
        assert getattr(config_with_files, key) == value


def test_config_files_lookup(config_with_files):
    for key, value in YAML_FILE_DATA[YAML_CONFIG_FILE_NAME].iteritems():
        lookup_key = 'lookup_{}'.format(key)
        setattr(config_with_files, lookup_key, '(( lookup | {} | (( {} )) ))'.format(YAML_LOOKUP_FILE_NAME, key))
        assert getattr(config_with_files, lookup_key) == YAML_FILE_DATA[YAML_LOOKUP_FILE_NAME][value]


def test_config_files_lookup_error(config_with_files):
    for key, value in YAML_FILE_DATA[YAML_CONFIG_FILE_NAME].iteritems():
        lookup_key = 'lookup_{}'.format(key)
        setattr(config_with_files, lookup_key, '(( lookup | {} ))'.format(YAML_LOOKUP_FILE_NAME))
        with pytest.raises(ConfigException):
            getattr(config_with_files, lookup_key)


def test_config_file_missing():
    with pytest.raises(ConfigLoadException):
        Config(config_file_name = MISSING_FILE_NAME)


@pytest.fixture(
    params = YAML_BAD_STRING_LIST
)
def yaml_file_with_bad_data(request, temp_dir):
    file_data = request.param
    file_name_full = os.path.join(temp_dir, YAML_CONFIG_FILE_NAME)
    with open(file_name_full, 'w') as file_object:
        file_object.write(file_data)

    return file_name_full


def test_config_file_bad_data(yaml_file_with_bad_data):
    with pytest.raises(ConfigLoadException):
        Config(config_file_name = yaml_file_with_bad_data)


# Config from string

@pytest.mark.parametrize(
    'config_data',
    (
        {
            'a': 1,
            'b': 2,
        },
        {
            'a': [
                1,
                2,
                {
                    'b': 3,
                    'c': 'def'
                }
            ],
        },
    )
)
def test_config_from_string(config_data):
    config_data_string = safe_dump(config_data)
    config = Config(config_string = config_data_string)
    for key, val in config_data.iteritems():
        check_expected(getattr(config, key), val)


def check_expected(data, expected):
    if isinstance(expected, dict):
        for key, val in expected.iteritems():
            check_expected(data[key], val)

    elif isinstance(expected, list):
        for data_val, expected_val in zip(data, expected):
            check_expected(data_val, expected_val)

    else:
        assert data == expected


@pytest.mark.parametrize(
    'yaml_bad_str',
    YAML_BAD_STRING_LIST
)
def test_config_from_string_bad(yaml_bad_str):
    with pytest.raises(ConfigLoadException):
        Config(config_string = yaml_bad_str)
