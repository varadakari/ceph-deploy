from urlparse import urlparse

from ceph_deploy.lib import remoto
from ceph_deploy.util import pkg_managers
from ceph_deploy.util.paths import gpg


def install(distro, version_kind, version, adjust_repos, **kw):
    # note: when split packages for ceph land for Debian/Ubuntu,
    # `kw['components']` will have those. Unused for now.
    codename = distro.codename
    machine = distro.machine_type

    if version_kind in ['stable', 'testing']:
        key = 'release'
    else:
        key = 'autobuild'

    # Make sure ca-certificates is installed
    remoto.process.run(
        distro.conn,
        [
            'env',
            'DEBIAN_FRONTEND=noninteractive',
            'apt-get',
            '-q',
            'install',
            '--assume-yes',
            'ca-certificates',
        ]
    )

    if adjust_repos:
        # Wheezy does not like the git.ceph.com SSL cert
        protocol = 'https'
        if codename == 'wheezy':
            protocol = 'http'
        remoto.process.run(
            distro.conn,
            [
                'wget',
                '-O',
                '{key}.asc'.format(key=key),
                gpg.url(key, protocol=protocol),
            ],
            stop_on_nonzero=False,
        )

        remoto.process.run(
            distro.conn,
            [
                'apt-key',
                'add',
                '{key}.asc'.format(key=key)
            ]
        )

        if version_kind == 'stable':
            url = 'http://ceph.com/debian-{version}/'.format(
                version=version,
                )
        elif version_kind == 'testing':
            url = 'http://ceph.com/debian-testing/'
        elif version_kind == 'dev':
            url = 'http://gitbuilder.ceph.com/ceph-deb-{codename}-{machine}-basic/ref/{version}'.format(
                codename=codename,
                machine=machine,
                version=version,
                )
        else:
            raise RuntimeError('Unknown version kind: %r' % version_kind)

        # set the repo priority for the right domain
        fqdn = urlparse(url).hostname
        distro.conn.remote_module.set_apt_priority(fqdn)
        distro.conn.remote_module.write_sources_list(url, codename)

    remoto.process.run(
        distro.conn,
        ['apt-get', '-q', 'update'],
        )

    # TODO this does not downgrade -- should it?
    remoto.process.run(
        distro.conn,
        [
            'env',
            'DEBIAN_FRONTEND=noninteractive',
            'DEBIAN_PRIORITY=critical',
            'apt-get',
            '-q',
            '-o', 'Dpkg::Options::=--force-confnew',
            '--no-install-recommends',
            '--assume-yes',
            'install',
            '--',
            'ceph',
            'ceph-mds',
            'ceph-common',
            'ceph-fs-common',
            'radosgw',
            # ceph only recommends gdisk, make sure we actually have
            # it; only really needed for osds, but minimal collateral
            'gdisk',
            ],
        )

def local_deb_install(distro, local_path):
    seq = ['librados', 'librbd', 'libcephfs1', 'python-ceph', 'ceph-common', 'ceph_']

    # Install packages one by one
    (out, err, status) = remoto.process.check(
        distro.conn,
        [
            'ls',
            local_path+'/'
        ]
    )

    if status != 0:
        raise RuntimeError(err)

    """
    remoto.process.run(
        distro.conn,
        [
            'apt-get',
            '-y',
            'install',
            'gdebi-core'
        ],
        stop_on_nonzero=False,
    )
    """

    # install packages in sequence.
    debs = out
    to_be_installed_debs = out

    for pkg in seq:
        for deb in debs:
            if deb.find(pkg) != -1:
                remoto.process.run(
                    distro.conn,
                    [
                        'dpkg',
                        '-i',
                        local_path+'/'+deb
                    ],
                    stop_on_nonzero=False,
                )
                to_be_installed_debs.remove(deb)

    # Install any remaining packages
    for deb in to_be_installed_debs:
        remoto.process.run(
            distro.conn,
            [
                'dpkg',
                '-i',
                local_path+'/'+deb
            ],
            stop_on_nonzero=False,
        )


def mirror_install(distro, repo_url, gpg_url, adjust_repos, **kw):
    # note: when split packages for ceph land for Debian/Ubuntu,
    # `kw['components']` will have those. Unused for now.
    repo_url = repo_url.strip('/')  # Remove trailing slashes
    gpg_path = gpg_url.split('file://')[-1]

    if adjust_repos:
        if not gpg_url.startswith('file://'):
            remoto.process.run(
                distro.conn,
                [
                    'wget',
                    '-O',
                    'release.asc',
                    gpg_url,
                ],
                stop_on_nonzero=False,
            )

        gpg_file = 'release.asc' if not gpg_url.startswith('file://') else gpg_path
        remoto.process.run(
            distro.conn,
            [
                'apt-key',
                'add',
                gpg_file,
            ]
        )

        # set the repo priority for the right domain
        fqdn = urlparse(repo_url).hostname
        distro.conn.remote_module.set_apt_priority(fqdn)

        distro.conn.remote_module.write_sources_list(repo_url, distro.codename)

    pkg_managers.apt_update(distro.conn)
    packages = (
        'ceph',
        'ceph-mds',
        'ceph-common',
        'ceph-fs-common',
        # ceph only recommends gdisk, make sure we actually have
        # it; only really needed for osds, but minimal collateral
        'gdisk',
    )

    pkg_managers.apt(distro.conn, packages)
    pkg_managers.apt(distro.conn, 'ceph')


def repo_install(distro, repo_name, baseurl, gpgkey, **kw):
    # do we have specific components to install?
    # removed them from `kw` so that we don't mess with other defaults
    # note: when split packages for ceph land for Debian/Ubuntu, `packages`
    # can be used. Unused for now.
    packages = kw.pop('components', [])
    # Get some defaults
    safe_filename = '%s.list' % repo_name.replace(' ', '-')
    install_ceph = kw.pop('install_ceph', False)
    baseurl = baseurl.strip('/')  # Remove trailing slashes

    if gpgkey:
        remoto.process.run(
            distro.conn,
            [
                'wget',
                '-O',
                'release.asc',
                gpgkey,
            ],
            stop_on_nonzero=False,
        )

    remoto.process.run(
        distro.conn,
        [
            'apt-key',
            'add',
            'release.asc'
        ]
    )

    distro.conn.remote_module.write_sources_list(
        baseurl,
        distro.codename,
        safe_filename
    )

    # set the repo priority for the right domain
    fqdn = urlparse(baseurl).hostname
    distro.conn.remote_module.set_apt_priority(fqdn)

    # repo is not operable until an update
    pkg_managers.apt_update(distro.conn)

    if install_ceph:
        # Before any install, make sure we have `wget`
        packages = (
            'ceph',
            'ceph-mds',
            'ceph-common',
            'ceph-fs-common',
            # ceph only recommends gdisk, make sure we actually have
            # it; only really needed for osds, but minimal collateral
            'gdisk',
        )

        pkg_managers.apt(distro.conn, packages)
        pkg_managers.apt(distro.conn, 'ceph')
