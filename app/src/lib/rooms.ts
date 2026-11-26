import type { ImageSourcePropType } from 'react-native';

// Demo photos (free Pexels images). Replace the files in assets/rooms with the
// hotel's own photos when they exist; keep the same names.
const PHOTOS: ImageSourcePropType[] = [
  require('@/assets/rooms/room-1.jpg'),
  require('@/assets/rooms/room-2.jpg'),
  require('@/assets/rooms/room-3.jpg'),
];

export const allPhotos = PHOTOS;
// A wide crop of the best room photo, made for the search screen header.
export const heroPhoto: ImageSourcePropType = require('@/assets/rooms/hero.jpg');

/** The same room type always gets the same photo. */
export function roomPhoto(roomType: string | null | undefined): ImageSourcePropType {
  const key = (roomType ?? '').toLowerCase();
  let hash = 0;
  for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  return PHOTOS[hash % PHOTOS.length];
}
