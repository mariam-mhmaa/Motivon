from datasets import load_dataset

targets = [
    ('herutriana44/hijab_dataset', 'train'),
    ('huggan/CelebA-faces-with-attributes', 'train'),
]

for name, split in targets:
    print(f"\n=== {name} [{split}] ===")
    try:
        ds = load_dataset(name, split=split)
        print('columns:', list(ds.column_names))
        sample = ds[0]
        non_image = {}
        for k, v in sample.items():
            tname = type(v).__name__
            if tname in ('Image', 'PngImageFile', 'JpegImageFile'):
                continue
            if hasattr(v, 'size') and hasattr(v, 'mode'):
                continue
            non_image[k] = v
        print('sample_non_image_fields:', non_image)
    except Exception as e:
        print('exception:', str(e))
