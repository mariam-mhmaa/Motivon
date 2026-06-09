from datasets import load_dataset

targets = [
    ('herutriana44/hijab_dataset', 'train'),
    ('huggan/CelebA-faces-with-attributes', 'train'),
]

for name, split in targets:
    print('\n=== {} [{}] ==='.format(name, split))
    try:
        ds = load_dataset(name, split=split, streaming=True, trust_remote_code=True)
        first = next(iter(ds))
        print('columns:', list(first.keys()))
        non_image = {}
        for k, v in first.items():
            tname = type(v).__name__
            if tname in ('Image', 'PngImageFile', 'JpegImageFile'):
                continue
            if hasattr(v, 'size') and hasattr(v, 'mode'):
                continue
            non_image[k] = v
        print('sample_non_image_fields:', non_image)
    except Exception as e:
        print('exception:', str(e))
