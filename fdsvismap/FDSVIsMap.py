import numpy as np
from skimage.draw import line
import matplotlib.pyplot as plt
import matplotlib.colors

import fdsreader as fds
from .helper_functions import *

class VisMap:
    def __init__(self, sim_dir, min_vis=0, max_vis=30):
        self.sim_dir = sim_dir
        self.slc = None
        self.start_point = None
        self.way_points_list = []
        self.mean_extco_array_list = []
        self.view_array_list = []
        self.distance_array_list = []
        self.vismap_list = []
        self.colission_array_list = []
        self.delta_array_list = []
        self.min_vis = min_vis # minimum visibility to be required #Todo: set individual for each waypoint
        self.max_vis = max_vis # maximum visibility to be considered #Todo: set individual for each waypoint
        self.background_image = None
        self.view_angle = True
        self.absolute_boolean_vismap_dict = {}
        self.time_agglomerated_absolute_boolean_vismap = None
        self._read_fds_data()

    def _get_waypoint_parameters(self, waypoint_id):
        return self.way_points_list[waypoint_id]

    def set_start_point(self, x, y):
        self.start_point = (x, y)

    def set_waypoint(self, x, y, c=3, ior=None):
        '''
        :param x: X coordinate of waypoint referring to global FDS coordinates
        :param y: Y coordinate of waypoint referring to global FDS coordinates
        :param c: Contrast factor for exit sign according to JIN
        :param ior: Orientation of the exit sign according to FDS orientations
        :return: adds waypoint to self.way_points_list
        '''
        self.way_points_list.append((x, y, c, ior))

    def _read_fds_data(self, quantity='OD_C0.9H0.1', slice=None): #: Todo: specify slice
        '''
        :param quantity: Quantity of FDS slice file to be evaluated
        :param slice: Index of FDS slice file to be evaluated
        :return:
        '''
        quantity = 'ext_coef_C0.9H0.1'
        # quantity = 'VIS_C0.9H0.1'
        sim = fds.Simulation(self.sim_dir)
        print(sim.slices)
        self.slc = sim.slices.filter_by_quantity(quantity)[0]
        self.obstructions = sim.obstructions
        self.all_x_coords = self.slc.coordinates["x"]
        self.all_y_coords = self.slc.coordinates["y"]

    def _get_extco_array(self, timestep):
        time_index = self.slc.get_nearest_timestep(timestep)
        data = self.slc.to_global_nonuniform()[time_index]
        extco_array = data
        return extco_array

    def _get_mean_extco_array(self, waypoint_id, timestep):
        waypoint = self._get_waypoint_parameters(waypoint_id)
        x = waypoint[0]
        y = waypoint[1]
        extco_array = self._get_extco_array(timestep)
        i_ref = find_closest_point(self.all_x_coords, x)
        j_ref = find_closest_point(self.all_y_coords, y)
        mean_extco_array = np.zeros_like(extco_array)
        for i, x in enumerate(self.all_x_coords):
            for j, y in enumerate(self.all_y_coords):
                img = np.zeros_like(extco_array)
                rr, cc = line(i_ref, j_ref, i, j)
                img[rr, cc] = 1
                n_cells = np.count_nonzero(img)
                mean_extco = np.sum(extco_array * img) / n_cells
                mean_extco_array[i, j] = mean_extco
        return mean_extco_array

    def _get_dist_array(self, waypoint_id):
        '''
        :param ref_point: point of interest
        :return: array containing distances to ref_point
        '''
        waypoint = self._get_waypoint_parameters(waypoint_id)
        x = waypoint[0]
        y = waypoint[1]
        self.xv, self.yv = np.meshgrid(self.all_x_coords, self.all_y_coords)
        distance_array = np.sqrt((self.xv - x)**2 + (self.yv - y)**2)
        self.distance_array_list.append(distance_array)
        return distance_array

    def _get_view_array(self, waypoint_id):
        distance_array = self._get_dist_array(waypoint_id)
        waypoint = self._get_waypoint_parameters(waypoint_id)
        x = waypoint[0]
        y = waypoint[1]
        ior = waypoint[3]

        # calculate cosinus for every cell from total distance and x / y distance
        if self.view_angle == True and ior != None:
            if ior == 1 or ior == -1:
                view_angle_array = abs((self.xv - x) / distance_array)
            elif ior == 2 or ior == -2:
                view_angle_array = abs((self.yv - y) / distance_array)
        else:
            view_angle_array = np.ones_like(distance_array)

        #  set visibility to zero on all cells that are behind the waypoint and against view direction
        if ior == -1:
            view_array = np.where(self.xv < x, view_angle_array, 0)
        elif ior == 1:
            view_array = np.where(self.xv > x, view_angle_array, 0)
        elif ior == -2:
            view_array = np.where(self.yv < y, view_angle_array, 0)
        elif ior == 2:
            view_array = np.where(self.yv > y, view_angle_array, 0)
        else:
            view_array = view_angle_array
        self.view_array_list.append(view_array)
        return view_array

    def _get_col_array(self, waypoint_id, z):
        waypoint = self._get_waypoint_parameters(waypoint_id)
        x_start = waypoint[0]
        y_start = waypoint[1]
        i_ref = find_closest_point(self.all_x_coords, x_start)
        j_ref = find_closest_point(self.all_y_coords, y_start)
        extco_array = self._get_extco_array(0)
        obst_array = np.zeros_like(extco_array)
        for obst in self.obstructions:
            for sub_obst in obst:
                _, x_extend, y_extend, z_extend = sub_obst.extent
                if z_extend[0] <= z <= z_extend[1]:
                    x_i_min = (np.abs(self.all_x_coords - x_extend[0])).argmin()
                    x_i_max = (np.abs(self.all_x_coords - x_extend[1])).argmin()
                    y_i_min = (np.abs(self.all_y_coords - y_extend[0])).argmin()
                    y_i_max = (np.abs(self.all_y_coords - y_extend[1])).argmin()
                    obst_array[x_i_min:x_i_max, y_i_min:y_i_max] = True
        obst_array = np.flip(obst_array, axis=1)
        final = np.zeros_like(obst_array)
        b = final.copy()
        edges = np.ones_like(obst_array)
        edges[1:-1, 1:-1] = False
        edge_x, edge_y = np.where(edges == True)
        for i, j in zip(edge_x, edge_y):
            b_x, b_y = line(i_ref, j_ref, i, j)
            b[b_x, b_y] = True
            cuts = np.where((obst_array == True) & (b == True))
            if cuts[0].size != 0:
                x_cut_coord = np.in1d(b_x, cuts[0])
                x_cut_index = np.where(x_cut_coord == True)[0][0]
                final[b_x[:x_cut_index], b_y[:x_cut_index]] = True
            else:
                final[b_x, b_y] = True
            b = final.copy()
        self.colission_array_list.append(final.T)
        return final.T

    def _get_vismap(self, waypoint_id, timestep):
        waypoint = self._get_waypoint_parameters(waypoint_id)
        mean_extco_array = self._get_mean_extco_array(waypoint_id, timestep)
        c = waypoint[2]
        vis_array = c / mean_extco_array.T
        vismap = np.where(vis_array > self.max_vis, self.max_vis, vis_array).astype(float)
        return vismap

    def get_bool_vismap(self, waypoint_id, timestep, extinction=True, viewangle=True, colission=True, z=2):#TODO: make z value changable
        if viewangle == True:
            view_array = self._get_view_array(waypoint_id)
        else:
            view_array = 1
        if extinction == True:
            vismap = self._get_vismap(waypoint_id, timestep)
        else:
            vismap = self.max_vis
        distance_array = self._get_dist_array(waypoint_id)
        if colission == True:
            colission_array = self._get_col_array(waypoint_id, z)
        else:
            colission_array = 1
        vismap_total = view_array * vismap * colission_array
        delta_map = np.where(vismap_total >= distance_array, True, False)
        delta_map = np.where(vismap_total < self.min_vis, False, delta_map)
        return delta_map

    def get_abs_bool_vismap(self, timestep, extinction=True, viewangle=True):
        boolean_vismap_list = []
        for waypoint_id, waypoint in enumerate(self.way_points_list):
            boolean_vismap = self.get_bool_vismap(waypoint_id, timestep, extinction=extinction, viewangle=viewangle)
            boolean_vismap_list.append(boolean_vismap)
            absolute_boolean_vismap = np.logical_or.reduce(boolean_vismap_list)
            self.absolute_boolean_vismap_dict[timestep] = absolute_boolean_vismap
        return absolute_boolean_vismap

    def get_time_aggl_abs_bool_vismap(self):
        self.time_agglomerated_absolute_boolean_vismap = np.logical_and.reduce(list(self.absolute_boolean_vismap_dict.values()))
        return self.time_agglomerated_absolute_boolean_vismap

    def plot_abs_bool_vismap(self): # Todo: is duplicate of plot_time_agglomerated_absolute_boolean_vismap
        # if self.time_agglomerated_absolute_boolean_vismap == None:
        #     self.get_time_agglomerated_absolute_boolean_vismap()
        extent = (self.all_x_coords[0], self.all_x_coords[-1], self.all_y_coords[-1], self.all_y_coords[0])
        if self.background_image is not None:
            plt.imshow(self.background_image, extent=extent)
        cmap = matplotlib.colors.ListedColormap(['red', 'green'])

        plt.imshow(self.absolute_boolean_vismap_dict, cmap=cmap, extent=extent, alpha=0.3)
        x, y, _, _ = zip(*self.way_points_list)
        plt.plot((self.start_point[0], *x), (self.start_point[1], *y), color='darkgreen', linestyle='--')
        plt.scatter((self.start_point[0], *x), (self.start_point[1], *y), color='darkgreen')
        plt.xlabel("X / m")
        plt.ylabel("Y / m")

    def add_background_image(self, file):
        self.background_image = plt.imread(file)

    def plot_time_aggl_abs_bool_vismap(self):
        # if self.time_agglomerated_absolute_boolean_vismap == None:
        #     self.get_time_agglomerated_absolute_boolean_vismap()
        extent = (self.all_x_coords[0], self.all_x_coords[-1], self.all_y_coords[-1], self.all_y_coords[0])
        if self.background_image is not None:
            plt.imshow(self.background_image, extent=extent)
        cmap = matplotlib.colors.ListedColormap(['red', 'green'])

        plt.imshow(self.time_agglomerated_absolute_boolean_vismap, cmap=cmap, extent=extent, alpha=0.5)
        x, y, _, _ = zip(*self.way_points_list)
        plt.plot((self.start_point[0], *x),(self.start_point[1], *y), color='darkgreen', linestyle='--')
        plt.scatter((self.start_point[0], *x),(self.start_point[1], *y), color='darkgreen')
        for wp_id, waypoint in enumerate(self.way_points_list):
            x = waypoint[0]
            y = waypoint[1]
            c = waypoint[2]
            ior = waypoint[3]
            plt.annotate(f"WP : {wp_id:>}\nC : {c:>}\nIOR : {ior}", xy=(x+0.3, y+1.5),  bbox=dict(boxstyle="round", fc="w"), fontsize=6)
        plt.xlabel("X / m")
        plt.ylabel("Y / m")
        plt.show()
