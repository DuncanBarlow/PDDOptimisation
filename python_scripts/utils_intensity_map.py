import numpy as np
import os


def angle2moll(theta, phi):
    
    latitude = np.pi / 2.0 - theta
    if phi < np.pi:
        longitude = phi
    else:
        longitude = phi - 2.0 * np.pi
    
    rad = 1.0 / np.sqrt(2.0)
    longitude0 = 0.0
    i=0
    angle1 = latitude
    dangle = 0.1
    while (i < 100) and (abs(dangle) > 0.01):
        angle2 = angle1 - (2.0 * angle1 + np.sin(2.0 * angle1) - np.pi * np.sin(latitude)) / (4.0 * np.cos(angle1)**2)
        dangle = abs(angle2 - angle1)
        angle1 = angle2
        i+=1
    x = rad * 2.0 * np.sqrt(2.0) / np.pi * (longitude - longitude0) * np.cos(angle2)
    y = rad * np.sqrt(2.0) * np.sin(angle2)
    
    return x, y



def extract_rms(intensity_map_normalized):

    rms = np.sqrt(np.mean(intensity_map_normalized**2))

    return rms



def print_save_readout(print_list, stats_filename):
    if os.path.exists(stats_filename):
        os.remove(stats_filename)
    file1 = open(stats_filename,"a")
    for line in range(len(print_list)):
        print(print_list[line])
        file1.writelines(print_list[line]+"\n")
    file1.close()



def readout_intensity(facility_spec, intensity_map, dataset_params, ind_profile):
    n_beams = facility_spec['nbeams']

    #rms
    intensity_map_normalised, avg_flux = imap_norm(intensity_map)
    imap_pn = np.sign(intensity_map_normalised)
    intensity_map_rms = 100.0 * np.sqrt(np.mean(intensity_map_normalised**2))

    print_line = []
    print_line.append('Number of beams ' + str(n_beams))
    #print_line.append('Max power per beam {:.2f}TW, '.format(facility_spec['default_power']))
    print_line.append('Evaluation radius {:.2f}um, '.format(dataset_params['illumination_evaluation_radii'][ind_profile]))

    print_line.append('RMS is {:.4f}%, '.format(intensity_map_rms))
    total_TW = None
    if dataset_params["run_plasma_profile"]:
        print_line.append('Mean ablation pressure: {:.2f}Mbar, '.format(avg_flux))
    else:
        total_TW = avg_flux*10**(-12) * 4.0 * np.pi
        mean_intensity_cm = avg_flux / (dataset_params['illumination_evaluation_radii'][ind_profile] / 10000.0)**2

        print_line.append('Mean intensity, {:.2e}W/cm2'.format(mean_intensity_cm))
        print_line.append('Mean intensity per steradian, {:.2e}W/sr'.format(avg_flux))
        print_line.append('The power per beam deposited is {:.4f}TW, '.format(total_TW / n_beams))
        print_line.append('The total power deposited is {:.2f}TW, '.format(total_TW))

    return print_line, total_TW



def heatsource_analysis(hs_and_modes):

    avg_flux = hs_and_modes["average_flux"][0]
    real_modes = hs_and_modes["complex_modes"][0,:]
    imag_modes = hs_and_modes["complex_modes"][1,:]

    return real_modes, imag_modes, avg_flux



def extract_run_parameters(iex, ind_profile, power_deposited, dataset_params, facility_spec, sys_params, deck_gen_params):

    total_power = 0
    print_line = []
    beam_count = 0
    num_vars = dataset_params["num_variables_per_beam"]

    theta_pointings_quad = np.zeros(facility_spec['nbeams'])
    cone_phi_offset = np.zeros(facility_spec['nbeams'])
    quad_list = list(set(facility_spec["Quad"]))

    for quad_name in quad_list:
        quad_slice = np.where(quad_name == facility_spec["Quad"])[0]

        quad_centre = np.sum(deck_gen_params['pointings'][iex,quad_slice],axis=0) / 4.0
        radius = np.sqrt(np.sum(quad_centre**2))
        theta_pointings_quad[quad_slice] = np.arccos(quad_centre[2] / radius)
        phi_pointings_quad = np.arctan2(quad_centre[1], quad_centre[0])

        cone_phi_offset[quad_slice] = phi_pointings_quad%(2*np.pi)-deck_gen_params["port_centre_phi"][quad_slice[0]]
    for icone in range(facility_spec['num_cones']):
        quad_name = facility_spec['quad_from_each_cone'][icone]
        quad_slice = np.where(facility_spec["Quad"] == quad_name)[0]
        quad_start_ind = quad_slice[0]
        beams_per_cone = facility_spec['beams_per_cone'][icone]

        cone_defocus = deck_gen_params["defocus"][iex,quad_start_ind]
        if dataset_params["time_varying_pulse"]:
            cone_powers = deck_gen_params["p0"][iex,quad_start_ind,ind_profile] / (
                          dataset_params['default_power'] * facility_spec["beams_per_ifriit_beam"])
        else:
            cone_powers = deck_gen_params["p0"][iex,quad_start_ind,0] / (
                          dataset_params['default_power'] * facility_spec["beams_per_ifriit_beam"])

        if ("quad_split_bool" in dataset_params.keys()) and dataset_params["quad_split_bool"]:
            quad_split_radius = 2. * dataset_params['target_radius'] / 1000 * np.sin(deck_gen_params["sim_params"][iex,icone*num_vars+dataset_params["quad_split_index"]]/2.0)
            if dataset_params["quad_split_skew_bool"]:
                quad_split_skew = deck_gen_params["sim_params"][iex,icone*num_vars+dataset_params["quad_split_skew_index"]]
            else:
                quad_split_skew = 0.0
        else:
            quad_split_radius = 0.0
            quad_split_skew = 0.0

        if icone < int(facility_spec['num_cones']/2):
            print_line.append("For cone " + str(icone+1) +
                  ": {:.2f}\N{DEGREE SIGN}, ".format(np.degrees(theta_pointings_quad[quad_start_ind])) +
                  "{:.2f}\N{DEGREE SIGN}, ".format(np.degrees(cone_phi_offset[quad_start_ind])) +
                  "{:.2f}mm, ".format(cone_defocus) +
                  "{:.2f}% power, ".format(cone_powers * 100) +
                  "{:.2f}mm qsplit,".format(quad_split_radius) +
                  "{:.2f}\N{DEGREE SIGN} qsplit".format(np.degrees(quad_split_skew)))

        total_power += cone_powers * beams_per_cone

    mean_power_fraction = total_power / facility_spec['nbeams']
    print_line.append('The optimization selected a mean power percentage, {:.2f}%, '.format(mean_power_fraction * 100.0))

    print_line.append('Total power emitted {:.2f}TW, '.format(total_power))
    if not dataset_params["run_plasma_profile"]:
        print_line.append('Percentage of emitted power deposited was {:.2f}%, '.format(power_deposited / (facility_spec["nbeams"] * dataset_params['default_power'] * mean_power_fraction) * 100.0))

    return print_line


def alms2rms(real_modes, imag_modes, lmax):

    # modes with m!=0 need to be x2 to account for negative terms
    # in healpix indexing the first lmax terms are all m=0
    pwr_spec_m0 = np.sum(np.abs(real_modes[:lmax]**2 + imag_modes[:lmax]**2))
    pwr_spec_rest = np.sum(np.abs(real_modes[lmax:]**2 + imag_modes[lmax:]**2)*2)
    rms = np.sqrt((pwr_spec_m0+pwr_spec_rest)/4.0/np.pi)

    return rms



def create_ytrain(pointing_per_cone, pointing_nside, defocus_per_cone, num_defocus, power_per_cone, num_powers):

    Y_train = np.hstack((np.array(pointing_per_cone)/(pointing_nside-1), np.array(defocus_per_cone)/(num_defocus-1)))
    Y_train = np.hstack((Y_train, np.array(power_per_cone)/(num_powers-1)))
    Y_norms = [pointing_nside, num_defocus, num_powers]

    return Y_train, Y_norms



def imap_norm(intensity_map):

    avg_flux = np.mean(intensity_map) # average power per steradian (i.e. a flux)
    intensity_map_normalized = intensity_map / avg_flux - 1.0

    return intensity_map_normalized, avg_flux
