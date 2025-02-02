import os
import sys
import ndjson
from configparser import ConfigParser
import argparse
from sklearn.preprocessing import MinMaxScaler

base_path = os.getcwd().split('sliver-maestro')[0]
base_path = os.path.join(base_path, "sliver-maestro")
sys.path.insert(1, base_path)
from src.utils.im_utils import *


config = ConfigParser()
config.read('config.cfg')


def adjust_output_images(initial_prefix, transparent_prefix, svg_base_path, svg=True):
    """
    Generates black drawing pixels with a transparent background.
    
    initial_prefix: str. path of raw outputs
    transparent_prefix: str. path of generated images
    svg_base_path: str. path to save images in svg format
    svg: bool. if True converts png to svg.
    """
    for t in range(5, 20):
        imgname = '%s_%d.png' % (initial_prefix, t)
        new_name = '%s_%d.png' % (transparent_prefix, t)
        s_img = cv2.imread(imgname)  # , -1)

        # set to 4 channels
        s_img = fourChannels(s_img)
        # remove white background
        s_img = cut(s_img)
        # set background transparent
        s_img = transBg(s_img)
        # img = s_img

        #gray = cv2.cvtColor(s_img, cv2.COLOR_BGR2GRAY)
        indices = np.where(s_img <= 160)
        s_img[indices] = 0
        indices = np.where(s_img > 160)
        s_img[indices] = 255

        img = cv2.bitwise_not(s_img)

        cv2.imwrite(new_name, img)
        # MC: check channels
        # and interchangeability of
        # cv2.imwrite(new_name, cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        img = cv2.imread(new_name)
        cv2.imwrite(new_name, img)

    if svg:
        for t in range(5, 20):
            imgname = '%s_%d.png' % (transparent_prefix, t)
            new_name = '%s_%d.svg' % (svg_base_path, t)
            s_img = cv2.imread(imgname)
            # img = cv2.bitwise_not(s_img)
            plt.imshow(s_img)
            plt.axis('off')
            plt.savefig(new_name, format='svg')

def generate_motion(svg_to_csv_base_path, scaled_base_path, final_motion):
    # Prepare for V-rep
    def scale_coordinates(svg_to_csv_base_path, scaled_base_path):
        """
        Scales and fits X and Y coordinates into the robot scene.
        """
        for i in range(17, 20):
            path = '%s_%d.csv' % (svg_to_csv_base_path, i)
            output_path = '%s_%d.csv' % (scaled_base_path, i)
            simple_co = np.genfromtxt(path, delimiter=',', skip_header=1,
                                      usecols=(1, 2, 3), dtype=np.float)
            scaler_x = MinMaxScaler(feature_range=(-0.4, 0.4))
            scaler_x.fit(simple_co[:, 0].reshape(-1, 1))
            simple_co_scaled_x = scaler_x.transform(simple_co[:, 0].reshape(-1, 1))
            scaler_y = MinMaxScaler(feature_range=(-0.2, 0.2))
            scaler_y.fit(simple_co[:, 1].reshape(-1, 1))
            simple_co_scaled_y = scaler_y.transform(simple_co[:, 1].reshape(-1, 1))

            df = pd.read_csv(path, index_col=0)
            df_scaled = df.copy(deep=True)

            df_scaled['X(m)'] = simple_co_scaled_x
            df_scaled['Y(m)'] = simple_co_scaled_y
            df_scaled['Z(m)'] = df_scaled['Z(m)'].apply(lambda x: 0.0 if x < 1 else 0.006)
            df_scaled.to_csv(output_path)

    def join_dframes(scaled_base_path, final_motion):
        """
        Combines dataframes that contains drawing sequence in each canvases

        scaled_base_path: str.
        final_motion: str.
        """

        full_frame = pd.DataFrame(columns=['X(m)', 'Y(m)', 'Z(m)'])
        for j in range(17, 20):
            path = '%s_%d.csv' % (scaled_base_path, j)
            df = pd.read_csv(path, index_col=0)
            full_frame = full_frame.append(df)

        seconds = [0.0]
        s = 0.0
        for i in range(len(full_frame)):
            s += 0.05
            seconds.append(s)

        full_frame['Seconds'] = seconds[:-1]
        full_frame = full_frame.set_index('Seconds')
        full_frame.to_csv(final_motion)

    scale_coordinates(svg_to_csv_base_path, scaled_base_path)
    join_dframes(scaled_base_path, final_motion)

def extract_raw_motion(raw_data, raw_motion, idx):
    with open(raw_data) as f:
        data = ndjson.load(f)

    drawings = data[idx]['drawing']
    strokes = len(drawings)
    df = pd.DataFrame(columns=['Seconds', 'X(m)', 'Y(m)', 'Z(m)'])
    for stroke in range(strokes):
        drawing = drawings[stroke]
        l_0 = np.array([drawing[0]])
        l_1 = np.array([drawing[1]])
        l_2 = np.array([drawing[2]])
        l = np.concatenate((l_0.T, l_1.T, l_2.T), axis=1)
        df_new = pd.DataFrame(l, columns=['X(m)', 'Y(m)', 'Seconds'])
        df_new['Z(m)'] = 0.0
        df_new['Z(m)'].iloc[-1] = 0.006
        df = df.append(df_new[['Seconds', 'X(m)', 'Y(m)', 'Z(m)']])

    scaler_x = MinMaxScaler(feature_range=(-0.4, 0.4))
    scaler_x.fit(df['X(m)'].values.reshape(-1, 1))
    df_scaled_x = scaler_x.transform(df['X(m)'].values.reshape(-1, 1))
    scaler_y = MinMaxScaler(feature_range=(-0.2, 0.2))
    scaler_y.fit(df['Y(m)'].values.reshape(-1, 1))
    df_scaled_y = scaler_y.transform(df['Y(m)'].values.reshape(-1, 1))

    df_scaled = df.copy(deep=True)

    df_scaled['X(m)'] = df_scaled_x
    df_scaled['Y(m)'] = df_scaled_y

    df_scaled['Seconds'] /= 1000
    df_scaled = df_scaled.set_index('Seconds')
    df_scaled.to_csv(raw_motion)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='sliver-maestro')
    parser.add_argument('-rp', '--rootpath')
    parser.add_argument('-category', '--category')
    parser.add_argument('-idx', '--idx')
    parser.add_argument('-svg', '--svg')
    args = parser.parse_args()
    root_path = args.rootpath
    category = args.category
    idx = args.idx
    svg = args.svg
    if not root_path:
        root_path = os.getcwd()
    if not category:
        category = 'cat'
    if not idx:
        idx = 0
    if not svg:
        svg = True

    initial_prefix = os.path.join(root_path, config['adjust_output_images']['initial_prefix'])
    transparent_prefix = os.path.join(root_path, config['adjust_output_images']['transparent_prefix'])

    svg_base_path = os.path.join(root_path, config['SVG']['svg_base_path'])
    svg_to_csv_base_path = os.path.join(root_path, config['SVG']['svg_to_csv_base_path'])

    adjust_output_images(initial_prefix=initial_prefix, transparent_prefix=transparent_prefix,
                         svg_base_path=svg_base_path, svg=svg)

    for i in range(17, 20):
        svg_file = '%s_%d.svg' % (svg_base_path, i)
        csv_path = '%s_%d.csv' % (svg_to_csv_base_path, i)
        parse_svg(svg_file=svg_file, csv_path=csv_path)

    scaled_base_path = os.path.join(root_path, config['generate_motion']['scaled_base_path'])
    final_motion = os.path.join(root_path, config['generate_motion']['final_motion'])
    raw_motion = os.path.join(root_path, config['generate_motion']['raw_motion'])
    raw_data = os.path.join(root_path, config['generate_motion']['raw_data'], category, category + '.ndjson')
    generate_motion(svg_to_csv_base_path=svg_to_csv_base_path, scaled_base_path=scaled_base_path,
                    final_motion=final_motion)
    extract_raw_motion(raw_data=raw_data, raw_motion=raw_motion, idx=idx)

