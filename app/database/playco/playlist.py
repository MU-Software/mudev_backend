import enum
import hashlib
import json
import requests
import sqlalchemy as sql
import typing
import urllib.parse

import app.common.utils as utils
import app.database as db_module
import app.database.user as user_module

db = db_module.db
safe_request_get_json = utils.ignore_exception(Exception, None)(lambda l: requests.get(l).json())
MAX_REDIRECT_CHECK = 4


class Playlist(db_module.DefaultModelMixin, db.Model):
    __tablename__ = 'TB_PLAYCO_PLAYLIST'
    uuid = db.Column(db_module.PrimaryKeyType,
                     db.Sequence('SQ_PlayCo_Playlist_UUID'),
                     primary_key=True,
                     nullable=False)
    user_id = db.Column(db_module.PrimaryKeyType, db.ForeignKey('TB_USER.uuid'), nullable=False)
    user: 'user_module.User' = db.relationship('User', primaryjoin=user_id == user_module.User.uuid)

    # Playlist index on user's playlist list. Reserved for later
    index = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String, nullable=False)
    description = db.Column(db.String, nullable=True)
    config_json = db.Column(db.String, nullable=True)

    blocked_at = db.Column(db.DateTime, nullable=True)
    why_blocked = db.Column(db.String, nullable=True)

    public_accessable = db.Column(db.Boolean, default=False, nullable=False)
    public_modifiable = db.Column(db.Boolean, default=False, nullable=False)
    public_item_appendable = db.Column(db.Boolean, default=False, nullable=False)
    public_item_orderable = db.Column(db.Boolean, default=False, nullable=False)
    public_item_deletable = db.Column(db.Boolean, default=False, nullable=False)
    allow_duplicate = db.Column(db.Boolean, default=True, nullable=False)

    def get_hash(self, as_str: bool = True) -> str | bytes:
        # TODO: Cache this value so that we don't need to query all items everytime
        #       when we call this function.
        hash_obj = hashlib.md5()
        hash_obj.update(
            self.to_json(
                include_info=True,
                include_items=False if self.blocked_at else True,
                include_count=False if self.blocked_at else True,
                include_hash=False).encode())
        hash_result: str = hash_obj.hexdigest()
        hash_result = self.commit_id + ':' + hash_result
        return hash_result if as_str else hash_result.encode()

    def __len__(self) -> int:
        if self.blocked_at:
            return 0

        return db.session.query(PlaylistItem)\
            .filter(PlaylistItem.playlist_id == self.uuid)\
            .count()

    def __bool__(self) -> bool:
        return bool(self.__len__)

    def __getitem__(self, index, return_query: bool = False):
        current_len = self.__len__()
        if not current_len:
            raise IndexError('list index out of range')
        # From now on, current_len won't be 0

        if isinstance(index, int):
            if not (-current_len <= index < current_len):
                raise IndexError('list index out of range')

            target_index = index % current_len
            target_query = db.session.query(PlaylistItem)\
                .filter(PlaylistItem.playlist_id == self.uuid)\
                .order_by(PlaylistItem.index)\
                .limit(1).offset(target_index)

            return target_query if return_query else target_query.first()
        elif isinstance(index, slice):
            start, stop, step = index.start or 0, index.stop or -1, index.step

            if step:
                raise NotImplementedError('step not supported here')
            if not (-current_len < start < current_len) or not (-current_len < stop < current_len):
                raise IndexError('list index out of range')

            start = start % current_len
            stop = stop % current_len
            result_limit = stop - start
            target_query = db.session.query(PlaylistItem)\
                .filter(PlaylistItem.playlist_id == self.uuid)\
                .order_by(PlaylistItem.index)\
                .limit(result_limit).offset(start)

            return target_query if return_query else target_query.all()
        elif isinstance(index, tuple):
            if not all(map(lambda x: -current_len < x < current_len, index)):
                raise IndexError('list index out of range')
            if return_query:
                raise ValueError('\'return_query=True\' on \'type(index) is tuple\' not supported')

            result: typing.List['PlaylistItem'] = [self[i] for i in index]  # Because of type hint
            return result
        elif index is Ellipsis:
            raise TypeError(f'{self.__class__.name} indices must be integers or slices, not ellipsis')
        else:
            raise TypeError(f'{self.__class__.name} indices must be integers or slices, not {type(index)}')

    def __setitem__(self, index, value) -> None:
        raise NotImplementedError(
                '__setitem__ is not implemented. \n'
                'If you want to change variables of element, \n'
                'change variables directly in element, and commit it.')

    def __delitem__(self, index, commit: bool = True) -> int:
        result = self.__getitem__(index)
        db.session.delete(result)

        if commit:
            db.session.commit()

        return result

    def clear(self, commit: bool = True) -> int:
        result = db.session.query(PlaylistItem).filter(PlaylistItem.playlist_id == self.uuid).delete()

        if commit:
            db.session.commit()

        return result

    def pop(self, index: int = -1):
        result = self[index]
        del self[index]
        return result

    def insert(self,
               index: int,
               link: str,
               added_by_id: int | None = None,
               commit: bool = True) -> 'PlaylistItem':
        # Create PlaylistItem
        new_item, failed_reason = PlaylistItem.gen(link)
        if (not new_item) or failed_reason:
            # link is not supported. raise Exception
            raise NotImplementedError(f'{failed_reason}:Link {link} not supported.')
        new_item.playlist = self
        new_item.added_by_id = added_by_id or self.user_id

        if not self.allow_duplicate:
            # Check if playlist already includes a link
            duplicate_check = db.session.query(PlaylistItem)\
                .filter(PlaylistItem.playlist_id == self.uuid)\
                .filter(
                    sql.or_(
                        PlaylistItem.link == new_item.link,
                        PlaylistItem.original_link == new_item.original_link,
                        sql.and_(
                            PlaylistItem.link_type == new_item.link_type,
                            PlaylistItem.link_id == new_item.link_id, ), ), )\
                .first()
            if duplicate_check:
                raise Exception(f'AlreadyIncluded:Link {link} already included')

        # calculate proper index
        if not len(self):
            # If the playlist is empty, add item as the first element.
            new_item.index = 0
        elif index == -1 or len(self) <= index:
            # Add item to last.
            # Inserted item's index should be largest of all.
            new_item.index = self[-1].index + 1
        elif index == 0:
            # Add object to first.
            # index can be negative.
            new_item.index = self[0].index - 1
        else:
            # Add item to wanted index. This task will take a while.
            # First, get items that will be former and next.
            target: tuple[PlaylistItem, PlaylistItem] = self[index-1:index]
            target_prev, target_next = target

            if (target_next.index - 1) != target_prev.index:
                # Great! there's a missing, uncontinuous number, we can use this.
                new_item.index = target_next.index - 1
            else:
                new_item.index = target_next.index
                # We need to modify the indexes of items in front or behind the target.
                # Choose the one with the smaller number between the front and the back.
                reorder_target: list[PlaylistItem]
                if (len(self) - index) < index:
                    # front is smaller
                    reorder_target = self[:index]
                    for t in reorder_target:
                        t.index -= 1
                else:
                    # back is smaller
                    reorder_target = self[index:]
                    for t in reorder_target:
                        t.index += 1

        # Add PlaylistItem on DB
        db.session.add(new_item)

        if commit:
            db.session.commit()

        return new_item

    def append(self, link: str, added_by_id: int | None = None, commit: bool = True) -> 'PlaylistItem':
        return self.insert(-1, link, added_by_id, commit)

    def get_all_items(self):
        return db.session.query(PlaylistItem)\
            .filter(PlaylistItem.playlist_id == self.uuid)\
            .order_by(PlaylistItem.index)\
            .all()

    def get_by_link(self, link: str, return_query: bool = False):
        target_query = db.session.query(PlaylistItem)\
            .filter(PlaylistItem.playlist_id == self.uuid)\
            .filter(sql.or_(
                PlaylistItem.link == link,
                PlaylistItem.original_link == link,
            ))

        if return_query:
            return target_query

        return target_query.all()

    def to_dict(self,
                include_info: bool = True,
                include_items: bool = True,
                include_count: bool = False,
                include_hash: bool = False):
        if self.blocked_at:
            return {
                'res_type': 'playco_playlist',
                'hash': self.get_hash(),

                'uuid': self.uuid,
                'index': self.index,
                'name': self.name,

                'blocked_at': self.blocked_at,
                'why_blocked': self.why_blocked,
            }

        result_dict = {
            'res_type': 'playco_playlist',

            'uuid': self.uuid,
            'index': self.index,
            'name': self.name,
            'description': self.description,

            'created_by_uuid': self.user_id,
            'created_by_nick': self.user.nickname,

            'allow_duplicate': self.allow_duplicate,
            'public_accessable': self.public_accessable,
            'public_modifiable': self.public_modifiable,
            'public_item_appendable': self.public_item_appendable,
            'public_item_deletable': self.public_item_deletable,
            'public_item_orderable': self.public_item_orderable,
        }

        if include_info:
            result_dict.update({'description': self.description, 'config': self.config_json, })

        if include_items:
            result_dict['items'] = [i.to_dict() for i in self.get_all_items()]

        if include_count:
            if 'items' in result_dict:
                result_dict['item_count'] = len(result_dict['items'])
            else:
                result_dict['item_count'] = len(self)

        if include_hash:
            result_dict['hash'] = self.get_hash()

        return result_dict

    def to_json(self,
                include_info: bool = True,
                include_items: bool = True,
                include_count: bool = True,
                include_hash: bool = True):
        return json.dumps(
            self.to_dict(
                include_info=include_info,
                include_items=include_items,
                include_count=include_count,
                include_hash=include_hash))


class PlaylistItemType(utils.EnumAutoName):
    youtube = enum.auto()
    unknown = enum.auto()

    @classmethod
    def domain_map(cls, domain) -> 'PlaylistItemType':
        return {
            'youtube.com': cls.youtube
        }.get(domain, cls.unknown)

    @classmethod
    def detect_url_type(cls, link: str) -> 'PlaylistItemType':
        session = requests.Session()
        session.max_redirects = MAX_REDIRECT_CHECK
        try:
            link_req = session.get(link)
        except requests.TooManyRedirects:
            return cls.unknown
        except Exception:
            return cls.unknown

        extracted_domain = '.'.join(urllib.parse.urlparse(link_req.url).netloc.split('.')[-2:])
        return cls.domain_map(extracted_domain)

    @classmethod
    def get_video_id_from_url(cls, link_type: 'PlaylistItemType', link: str) -> str:
        """
        Examples:
        - http://youtu.be/SA2iWivDJiE
        - http://www.youtube.com/watch?v=_oPAwA_Udwc&feature=feedu
        - http://www.youtube.com/embed/SA2iWivDJiE
        - http://www.youtube.com/v/SA2iWivDJiE?version=3&amp;hl=en_US
        """
        if link_type == cls.youtube:
            query = urllib.parse.urlparse(link)
            if query.hostname == 'youtu.be':
                return query.path[1:]
            if query.hostname in ('www.youtube.com', 'youtube.com'):
                if query.path == '/watch':
                    p = urllib.parse.parse_qs(query.query)
                    return p['v'][0]
                if query.path[:7] == '/embed/':
                    return query.path.split('/')[2]
                if query.path[:3] == '/v/':
                    return query.path.split('/')[2]
            # fail?
            return None
        elif link_type == cls.unknown:
            return None
        else:
            return None

    @classmethod
    def get_info(cls, link: str):
        INFO_MAP: dict[PlaylistItemType, typing.Any] = {
            cls.youtube: lambda l: safe_request_get_json('https://www.youtube.com/oembed?url='+link),
            cls.unknown: lambda l: None,
        }
        link_type = cls.detect_url_type(link)
        link_data = INFO_MAP[link_type](link)
        if link_type != cls.unknown and link_data:
            link_data['id'] = cls.get_video_id_from_url(link_type, link)

        return link_type, link_data


class PlaylistItem(db_module.DefaultModelMixin, db.Model):
    __tablename__ = 'TB_PLAYCO_PLAYLIST_ITEM'
    uuid = db.Column(db_module.PrimaryKeyType,
                     db.Sequence('SQ_PlayCo_PlaylistItem_UUID'),
                     primary_key=True,
                     nullable=False)

    playlist_id = db.Column(
                    db_module.PrimaryKeyType,
                    db.ForeignKey('TB_PLAYCO_PLAYLIST.uuid', ondelete='CASCADE'),
                    nullable=False)
    playlist: 'Playlist' = db.relationship(
                                'Playlist',
                                primaryjoin=playlist_id == Playlist.uuid,
                                backref=db.backref('items',
                                                   order_by='PlaylistItem.created_at.desc()',
                                                   cascade='all, delete-orphan'))
    added_by_id = db.Column(
                    db_module.PrimaryKeyType,
                    db.ForeignKey('TB_USER.uuid', ondelete='CASCADE'),
                    nullable=False)
    added_by: 'user_module.User' = db.relationship(
                                        'User',
                                        primaryjoin=added_by_id == user_module.User.uuid)

    index = db.Column(db.Integer, unique=False, nullable=False)  # Item's index on playlist
    name = db.Column(db.String, unique=False, nullable=True)
    data = db.Column(db.String, unique=False, nullable=True)
    preview_img = db.Column(db.String, unique=False, nullable=True)

    original_link = db.Column(db.String, unique=False, nullable=False)
    link = db.Column(db.String, unique=False, nullable=False)
    link_type = db.Column(db.String, unique=False, nullable=False)
    link_id = db.Column(db.String, unique=False, nullable=False)

    @classmethod
    def gen(cls, link: str):
        result_obj = cls()
        result_obj.original_link = str(link)
        result_obj.link_type, result_obj.data = PlaylistItemType.get_info(result_obj.original_link)

        if result_obj.link_type == PlaylistItemType.unknown:
            return None, 'NotSupported'
        elif result_obj.link_type == PlaylistItemType.youtube:
            if result_obj.data is None:
                return None, 'DataLoadFailed'

            # We need to simplify the YouTube link
            # as React-Player cannot play the url that includes 'list' query.
            result_obj.link = 'https://www.youtube.com/watch?v=' + result_obj.data['id']
            result_obj.link_id = result_obj.data['id']
            result_obj.name = result_obj.data['title']
            result_obj.preview_img = result_obj.data['thumbnail_url']
            result_obj.data = json.dumps(result_obj.data)

        result_obj.link_type = result_obj.link_type.value
        return result_obj, ''

    def to_dict(self):
        return {
            'uuid': self.uuid,
            'res_type': 'playco_playlist_item',
            'index': self.index,

            'added_by_uuid': self.added_by_id,
            'added_by_nick': self.added_by.nickname,

            'name': self.name,
            'data': self.data,
            'original_link': self.original_link,
            'link': self.link,
            'link_type': self.link_type,
            'link_id': self.link_id,

        }
