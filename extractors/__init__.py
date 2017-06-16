import logging
import re

from utils.loadsetting import tc, db, setting
from utils.pattern import pattern_group


class Autoseed(object):
    active_seed = []
    active_online_seed = []
    active_online_tracker = []

    downloading_torrent_queue = []

    def __init__(self):
        # Byrbt
        if setting.site_byrbt["status"]:
            from .byrbt import Byrbt
            autoseed_byrbt = Byrbt(site_setting=setting.site_byrbt)
            if autoseed_byrbt.status:
                self.active_seed.append(autoseed_byrbt)

        # NPUBits
        if setting.site_npubits["status"]:
            from .npubits import NPUBits
            autoseed_npubits = NPUBits(site_setting=setting.site_npubits)
            if autoseed_npubits.status:
                self.active_seed.append(autoseed_npubits)

        # nwsuaf6
        if setting.site_nwsuaf6["status"]:
            from .nwsuaf6 import MTPT
            autoseed_nwsuaf6 = MTPT(site_setting=setting.site_nwsuaf6)
            if autoseed_nwsuaf6.status:
                self.active_seed.append(autoseed_nwsuaf6)

        self.active_tracker = (site.db_column for site in self.active_seed)
        logging.info("The assign autoseed module:{lis}".format(lis=self.active_seed))

        self.reseed_site_online_check()

    def reseed_site_online_check(self):
        self.active_online_seed = (site for site in self.active_seed if site.online_check() and site.status)
        self.active_online_tracker = (site.db_column for site in self.active_online_seed)

    def feed(self, dl_torrent, cow):
        reseed_status = False

        tname = dl_torrent.name
        for pat in pattern_group:
            search = re.search(pat, tname)
            if search:
                logging.debug("The search group: {gr}".format(gr=search.groups()))
                key_raw = re.sub(r"[_\-.]", " ", search.group("search_name"))
                clone_dict = db.get_data_clone_id(key=key_raw)
                for site in self.active_online_seed:  # Site feed
                    if int(cow[site.db_column]) is 0:
                        tag = site.torrent_feed(torrent=dl_torrent, name_pattern=search, clone_db_dict=clone_dict)
                        db.reseed_update(did=dl_torrent.id, rid=tag, site=site.db_column)
                reseed_status = True
                break

        if not reseed_status:  # Update seed_id == -1 if no matched pattern
            logging.warning("No match pattern,Mark \"{}\" As Un-reseed torrent,Stop watching.".format(tname))
            for tracker in self.active_tracker:
                db.reseed_update(did=dl_torrent.id, rid=-1, site=tracker)

    def update(self):
        """Get the pre-reseed list from database."""
        self.reseed_site_online_check()
        result = db.get_table_seed_list_limit(tracker_list=self.active_online_tracker, operator="OR", condition="=0")
        for t in result:  # Traversal all un-reseed list
            try:
                dl_torrent = tc.get_torrent(t["download_id"])
            except KeyError:  # Un-exist pre-reseed torrent
                logging.error("The pre-reseed Torrent (which name: \"{0}\") isn't found in result,"
                              "It will be deleted from db in next delete-check time".format(t["title"]))
            else:
                tname = dl_torrent.name
                if int(dl_torrent.progress) is 100:  # Get the download progress in percent.
                    logging.info("New completed torrent: \"{name}\" ,Judge reseed or not.".format(name=tname))
                    self.feed(dl_torrent=dl_torrent, cow=t)
                    if dl_torrent.id in self.downloading_torrent_queue:
                        self.downloading_torrent_queue.pop(dl_torrent.id)
                elif dl_torrent.id in self.downloading_torrent_queue:
                    pass
                else:
                    logging.warning("Torrent:\"{name}\" is still downloading,Wait......".format(name=tname))
                    self.downloading_torrent_queue.append(dl_torrent.id)
