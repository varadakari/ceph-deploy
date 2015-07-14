from ceph_deploy.util import pkg_managers


def uninstall(conn, purge=False):
    packages = [
        'libcephfs1',
        'ceph',
        'ceph-mds',
        'ceph-common',
        'ceph-fs-common',
        'radosgw',
        ]
    pkg_managers.apt_remove(
        conn,
        packages,
        purge=purge,
    )
