import json
import os
import platform
import random
import re
import shutil
import string
import subprocess

import requests
from PySide6.QtCore import (
    Signal,
    Qt,
)
from PySide6.QtWidgets import (
    QMainWindow,
    QFileDialog,
    QVBoxLayout,
    QWidget,
    QPushButton,
    QListWidget,
    QHBoxLayout,
    QListWidgetItem,
    QLineEdit,
    QGridLayout, QCheckBox,
)
from PySide6.QtGui import (
    QColor,
)
from urlobject import URLObject
from urllib.parse import urlparse

from options import OptionsDialog


class ChannelList(QMainWindow):
    channels_loaded = Signal(list)

    def __init__(self, app, player, config_manager):
        super().__init__()
        self.app = app
        self.player = player
        self.config_manager = config_manager
        self.config = self.config_manager.config
        self.config_manager.apply_window_settings("channel_list", self)

        self.setWindowTitle("QiTV Channel List")
        # self.setWindowIcon(QIcon("qitv.ico"))

        self.container_widget = QWidget(self)
        self.setCentralWidget(self.container_widget)
        self.grid_layout = QGridLayout(self.container_widget)

        self.create_upper_panel()
        self.create_left_panel()
        self.create_media_controls()
        self.load_channels()

    def closeEvent(self, event):
        self.app.quit()
        self.player.close()
        self.config_manager.save_window_settings(self.geometry(), "channel_list")
        event.accept()

    def create_upper_panel(self):
        self.upper_layout = QWidget(self.container_widget)
        ctl_layout = QHBoxLayout(self.upper_layout)

        self.open_button = QPushButton("Open File")
        self.open_button.clicked.connect(self.open_file)
        ctl_layout.addWidget(self.open_button)

        self.options_button = QPushButton("Options")
        self.options_button.clicked.connect(self.options_dialog)
        ctl_layout.addWidget(self.options_button)
        self.grid_layout.addWidget(self.upper_layout, 0, 0)

    def create_left_panel(self):
        self.left_panel = QWidget(self.container_widget)
        left_layout = QVBoxLayout(self.left_panel)

        self.search_box = QLineEdit(self.left_panel)
        self.search_box.setPlaceholderText("Search channels...")
        self.search_box.textChanged.connect(self.filter_channels)
        left_layout.addWidget(self.search_box)

        self.channel_list = QListWidget(self.left_panel)
        self.channel_list.itemClicked.connect(self.channel_selected)
        left_layout.addWidget(self.channel_list)

        self.grid_layout.addWidget(self.left_panel, 1, 0)
        self.grid_layout.setColumnStretch(0, 1)

        # Add favorite button and action
        self.favorite_button = QPushButton("Favorite/Unfavorite")
        self.favorite_button.clicked.connect(self.toggle_favorite)
        left_layout.addWidget(self.favorite_button)

        # Add checkbox to show only favorites
        self.favorites_only_checkbox = QCheckBox("Show only favorites")
        self.favorites_only_checkbox.stateChanged.connect(self.filter_channels)
        left_layout.addWidget(self.favorites_only_checkbox)

        # add context menu for channel list
        self.channel_list.setContextMenuPolicy(Qt.ActionsContextMenu)

    def filter_channels(self, text):
        show_favorites = self.favorites_only_checkbox.isChecked()
        search_text = text.lower()

        for i in range(self.channel_list.count()):
            item = self.channel_list.item(i)
            channel_name = item.text().lower()

            matches_search = search_text in channel_name
            is_favorite = self.check_if_favorite(item.text())

            if show_favorites and not is_favorite:
                item.setHidden(True)
            else:
                item.setHidden(not matches_search)

    def toggle_favorite(self):
        selected_item = self.channel_list.currentItem()
        if selected_item:
            channel_name = selected_item.text()
            is_favorite = self.check_if_favorite(channel_name)
            if is_favorite:
                self.remove_from_favorites(channel_name)
            else:
                self.add_to_favorites(channel_name)

    def add_to_favorites(self, channel_name):
        if channel_name not in self.config["favorites"]:
            self.config["favorites"].append(channel_name)
            self.config_manager.save_config()

    def remove_from_favorites(self, channel_name):
        if channel_name in self.config["favorites"]:
            self.config["favorites"].remove(channel_name)
            self.config_manager.save_config()

    def check_if_favorite(self, channel_name):
        return channel_name in self.config["favorites"]

    def display_channels(self, channels):
        self.channel_list.clear()
        for channel in channels:
            item = QListWidgetItem(channel["name"])
            item.setData(1, channel["cmd"])
            self.channel_list.addItem(item)

            # Mark favorite channels
            if self.check_if_favorite(channel["name"]):
                item.setBackground(QColor("yellow"))  # Optional: change color for favorite channels

    def create_media_controls(self):
        self.media_controls = QWidget(self.container_widget)
        control_layout = QHBoxLayout(self.media_controls)

        self.play_button = QPushButton("Play/Pause")
        self.play_button.clicked.connect(self.player.toggle_play_pause)
        control_layout.addWidget(self.play_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.player.stop_video)
        control_layout.addWidget(self.stop_button)

        self.vlc_button = QPushButton("Open in VLC")
        self.vlc_button.clicked.connect(self.open_in_vlc)
        control_layout.addWidget(self.vlc_button)

        self.grid_layout.addWidget(self.media_controls, 2, 0)

    def open_in_vlc(self):
        # Invoke user's VLC player to open the current stream
        if self.link:
            try:
                if platform.system() == "Windows":
                    vlc_path = shutil.which("vlc")  # Try to find VLC in PATH
                    if not vlc_path:
                        program_files = os.environ.get(
                            "ProgramFiles", "C:\\Program Files"
                        )
                        vlc_path = os.path.join(
                            program_files, "VideoLAN", "VLC", "vlc.exe"
                        )
                    subprocess.Popen([vlc_path, self.link])

                elif platform.system() == "Darwin":  # macOS
                    vlc_path = shutil.which("vlc")  # Try to find VLC in PATH
                    if not vlc_path:
                        common_paths = [
                            "/Applications/VLC.app/Contents/MacOS/VLC",
                            "~/Applications/VLC.app/Contents/MacOS/VLC",
                        ]
                        for path in common_paths:
                            expanded_path = os.path.expanduser(path)
                            if os.path.exists(expanded_path):
                                vlc_path = expanded_path
                                break
                    subprocess.Popen([vlc_path, self.link])

                else:  # Assuming Linux or other Unix-like OS
                    vlc_path = shutil.which("vlc")  # Try to find VLC in PATH
                    subprocess.Popen([vlc_path, self.link])
                # when VLC open, stop running video on self.player
                self.player.stop_video()
            except FileNotFoundError as fnf_error:
                print("VLC not found: ", fnf_error)
            except Exception as e:
                print(f"Error opening VLC: {e}")

    def open_file(self):
        file_dialog = QFileDialog(self)
        file_path, _ = file_dialog.getOpenFileName()
        if file_path:
            self.player.play_video(file_path)

    def save_config(self):
        self.config_manager.save_config()

    def load_channels(self):
        selected_provider = self.config["data"][self.config["selected"]]
        config_type = selected_provider.get("type", "")
        if config_type == "M3UPLAYLIST":
            self.load_m3u_playlist(selected_provider["url"])
        elif config_type == "XTREAM":
            urlobject = URLObject(selected_provider["url"])
            if urlobject.scheme == "":
                urlobject = URLObject(f"http://{selected_provider['url']}")
            url = f"{urlobject.scheme}://{urlobject.netloc}/get.php?username={selected_provider['username']}&password={selected_provider['password']}&type=m3u"
            self.load_m3u_playlist(url)
        elif config_type == "STB":
            self.do_handshake(selected_provider["url"], selected_provider["mac"])
        elif config_type == "M3USTREAM":
            self.load_stream(selected_provider["url"])

    def load_m3u_playlist(self, url):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                channels = self.parse_m3u(response.text)
                self.display_channels(channels)
        except requests.RequestException as e:
            print(f"Error loading M3U Playlist: {e}")

    def load_stream(self, url):
        channel = {"id": 1, "name": "Stream", "cmd": url}
        self.display_channels([channel])

    def display_channels(self, channels):
        self.channel_list.clear()
        for channel in channels:
            item = QListWidgetItem(channel["name"])
            item.setData(1, channel["cmd"])
            self.channel_list.addItem(item)

    def channel_selected(self, item):
        cmd = item.data(1)
        if self.config["data"][self.config["selected"]]["type"] == "STB":
            url = self.create_link(cmd)
            if url:
                self.player.play_video(url)
            else:
                print("Failed to create link.")
        else:
            self.player.play_video(cmd)

    def options_dialog(self):
        options = OptionsDialog(self)
        options.exec_()

    @staticmethod
    def parse_m3u(data):
        lines = data.split("\n")
        result = []
        channel = {}
        id = 0
        for line in lines:
            if line.startswith("#EXTINF"):
                tvg_id_match = re.search(r'tvg-id="([^"]+)"', line)
                tvg_logo_match = re.search(r'tvg-logo="([^"]+)"', line)
                group_title_match = re.search(r'group-title="([^"]+)"', line)
                channel_name_match = re.search(r",(.+)", line)

                tvg_id = tvg_id_match.group(1) if tvg_id_match else None
                tvg_logo = tvg_logo_match.group(1) if tvg_logo_match else None
                group_title = group_title_match.group(1) if group_title_match else None
                channel_name = (
                    channel_name_match.group(1) if channel_name_match else None
                )

                id += 1
                channel = {"id": id, "name": channel_name}
            elif line.startswith("http"):
                urlobject = urlparse(line)
                channel["cmd"] = urlobject.geturl()
                result.append(channel)
        return result

    def do_handshake(self, url, mac, serverload="/server/load.php", load=True):
        token = (
            self.config.get("token")
            if self.config.get("token")
            else self.random_token(self)
        )
        options = self.create_options(url, mac, token)
        try:
            fetchurl = f"{url}{serverload}?type=stb&action=handshake&prehash=0&token={token}&JsHttpRequest=1-xml"
            handshake = requests.get(fetchurl, headers=options["headers"])
            body = handshake.json()
            token = body["js"]["token"]
            options["headers"]["Authorization"] = f"Bearer {token}"
            self.config["data"][self.config["selected"]]["options"] = options
            self.save_config()
            if load:
                self.load_stb_channels(url, options)
            return True
        except Exception as e:
            if serverload != "/portal.php":
                serverload = "/portal.php"
                return self.do_handshake(url, mac, serverload)
            print("Error in handshake:", e)
            return False

    def load_stb_channels(self, url, options):
        url = URLObject(url)
        url = f"{url.scheme}://{url.netloc}"
        try:
            fetchurl = f"{url}/server/load.php?type=itv&action=get_all_channels"
            response = requests.get(fetchurl, headers=options["headers"])
            result = response.json()
            channels = result["js"]["data"]
            self.display_channels(channels)
            self.config["data"][self.config["selected"]]["options"] = options
            self.save_config()
        except Exception as e:
            print(f"Error loading STB channels: {e}")

    def create_link(self, cmd):
        try:
            selected_provider = self.config["data"][self.config["selected"]]
            url = selected_provider["url"]
            url = URLObject(url)
            url = f"{url.scheme}://{url.netloc}"
            options = selected_provider["options"]
            fetchurl = f"{url}/server/load.php?type=itv&action=create_link&type=itv&cmd={requests.utils.quote(cmd)}&JsHttpRequest=1-xml"
            response = requests.get(fetchurl, headers=options["headers"])
            result = response.json()
            link = result["js"]["cmd"].split(" ")[-1]
            self.link = link
            return link
        except Exception as e:
            print(f"Error creating link: {e}")
            return None

    @staticmethod
    def random_token(self):
        return "".join(random.choices(string.ascii_letters + string.digits, k=32))

    @staticmethod
    def create_options(url, mac, token):
        url = URLObject(url)
        options = {
            "headers": {
                "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3",
                "Accept-Charset": "UTF-8,*;q=0.8",
                "X-User-Agent": "Model: MAG200; Link: Ethernet",
                "Host": f"{url.netloc}",
                "Range": "bytes=0-",
                "Accept": "*/*",
                "Referer": f"{url}/c/" if not url.path else f"{url}/",
                "Cookie": f"mac={mac}; stb_lang=en; timezone=Europe/Kiev; PHPSESSID=null;",
                "Authorization": f"Bearer {token}",
            }
        }
        return options

    def generate_headers(self):
        selected_provider = self.config["data"][self.config["selected"]]
        return selected_provider["options"]["headers"]

    @staticmethod
    def verify_url(url):
        try:
            response = requests.get(url)
            # return response.status_code == 200
            # basically we check if we can connect
            return True if response.status_code else False
        except Exception as e:
            print("Error verifying URL:", e)
            return False
