import numpy as np
import utils_deck_generation as idg
import healpy_pointings as hpoint
import netcdf_read_write as nrw
import utils_intensity_map as uim
import os
import subprocess
import sys
from scipy.stats import qmc


def define_system_params(root_dir):
    sys_params = {}
    sys_params["num_processes"] = 1
    sys_params["num_openmp_parallel"] = 4
    sys_params["num_ex_checkpoint"] = 10

    sys_params["run_gen_deck"] = True
    sys_params["run_sims"] = True
    sys_params["run_checkpoint"] = True
    sys_params["run_clean"] = False
    sys_params["run_plasma_profile"] = True
    if sys_params["run_plasma_profile"]:
        sys_params["num_profiles"] = 2 # change this
    else:
        sys_params["num_profiles"] = 1 # leave this

    sys_params["root_dir"] = root_dir
    sys_params["sim_dir"] = "run_"
    sys_params["trainingdata_filename"] = "training_data_and_labels.nc"
    sys_params["ifriit_ouput_name"] = "p_in_z1z2_beam_all.nc"
    sys_params["figure_location"] = "plots"
    sys_params["plot_file_type"] = ".pdf"
    sys_params["plasma_profile_dir"] = "plasma_profiles"
    sys_params["ifriit_input_name"] = "ifriit_inputs_base.txt"
    sys_params["plasma_profile_nc"] = "ifriit_1davg_input.nc"
    sys_params["heat_source_nc"] = "heat_source_all_beams.nc"
    sys_params["dataset_params_filename"] = "dataset_params.nc"
    sys_params["facility_spec_filename"] = "facility_spec.nc"
    sys_params["ifriit_binary_filename"] = "main"

    return sys_params



def define_dataset_params(num_examples,
                          random_sampling=0,
                          random_seed=12345):
    dataset_params = {}
    # Number of samples, size of NN training set
    dataset_params["num_examples"] = num_examples
    dataset_params["random_seed"] = random_seed
    dataset_params["hemisphere_symmetric"] = True
    dataset_params["imap_nside"] = 256

    num_variables_per_beam = 0
    # pointings
    dataset_params["surface_cover_radians"] = np.radians(45.0)
    dataset_params["theta_index"] = num_variables_per_beam
    num_variables_per_beam += 1
    dataset_params["phi_index"] = num_variables_per_beam
    num_variables_per_beam += 1
    # defocus
    dataset_params["defocus_default"] = 0.0
    dataset_params["defocus_range"] = 20.0 # mm
    dataset_params["defocus_bool"] = False
    if dataset_params["defocus_bool"]:
        dataset_params["defocus_index"] = num_variables_per_beam
        num_variables_per_beam += 1
    #power
    dataset_params["min_power"] = 0.5 # fraction of full power
    dataset_params["power_index"] = num_variables_per_beam
    num_variables_per_beam += 1
    dataset_params["num_variables_per_beam"] = num_variables_per_beam

    dataset_params["run_type"] = "lmj" #"test" #"lmj" #"nif"
    if dataset_params["run_type"] == "nif":
        facility_spec = idg.import_nif_config()
    elif (dataset_params["run_type"] == "lmj") or (dataset_params["run_type"] == "test"):
        facility_spec = idg.import_lmj_config()

    dataset_params["LMAX"] = 30
    dataset_params["num_coeff"] = int(((dataset_params["LMAX"] + 2) * (dataset_params["LMAX"] + 1))/2.0)
    # Assume symmetry
    dataset_params["num_input_params"] = int(facility_spec['num_cones']/2) * dataset_params["num_variables_per_beam"]

    random_generator=np.random.default_rng(dataset_params["random_seed"])
    if random_sampling == 1:
        print("Random Sampling!")
        sample = random_generator.random((dataset_params["num_examples"], dataset_params["num_input_params"]))
    else:
        sampler = qmc.LatinHypercube(d=dataset_params["num_input_params"],
                                     strength=1, seed=random_generator, optimization="random-cd")
        sample = sampler.random(n=dataset_params["num_examples"])
    dataset_params["Y_train"] = sample.T

    return dataset_params, facility_spec



def define_dataset(dataset_params, sys_params):
    dataset = {}
    dataset["num_evaluated"] = 0
    dataset["input_parameters"] = np.zeros((dataset_params["num_examples"], dataset_params["num_input_params"]))
    dataset["real_modes"] = np.zeros((dataset_params["num_examples"], sys_params["num_profiles"], dataset_params["num_coeff"]))
    dataset["imag_modes"] = np.zeros((dataset_params["num_examples"], sys_params["num_profiles"], dataset_params["num_coeff"]))
    dataset["avg_flux"] = np.zeros((dataset_params["num_examples"], sys_params["num_profiles"]))
    dataset["rms"] = np.zeros((dataset_params["num_examples"], sys_params["num_profiles"]))
    return dataset



def generate_training_data(dataset_params, sys_params, facility_spec):
    nrw.save_general_netcdf(dataset_params, sys_params["root_dir"] + "/" + sys_params["dataset_params_filename"])
    nrw.save_general_netcdf(facility_spec, sys_params["root_dir"] + "/" + sys_params["facility_spec_filename"])
    dataset_params = idg.create_run_files(dataset_params, sys_params, facility_spec)

    dataset = define_dataset(dataset_params, sys_params)
    dataset["input_parameters"] = dataset_params["Y_train"].T

    min_parallel = 0
    max_parallel = -1
    chkp_marker = 1.0
    run_location = sys_params["root_dir"] + "/" + sys_params["sim_dir"]
    filename_trainingdata = sys_params["root_dir"] + "/" + sys_params["trainingdata_filename"]
    if sys_params["run_sims"]:
        num_parallel_runs = int(dataset_params["num_examples"] / sys_params["num_processes"])
        if num_parallel_runs > 0:
            for ir in range(num_parallel_runs):
                min_parallel = ir * sys_params["num_processes"]
                max_parallel = (ir + 1) * sys_params["num_processes"] - 1
                dataset = run_and_delete(min_parallel, max_parallel, dataset, dataset_params, sys_params, facility_spec)

                if sys_params["run_checkpoint"]:
                    if ((max_parallel + 1) >= (chkp_marker * sys_params["num_ex_checkpoint"])):
                        print("Save training data checkpoint at run: " + str(max_parallel))
                        dataset["num_evaluated"] = max_parallel
                        nrw.save_general_netcdf(dataset, filename_trainingdata)
                        chkp_marker +=1

        if max_parallel != (dataset_params["num_examples"] - 1):
            min_parallel = max_parallel + 1
            max_parallel = dataset_params["num_examples"] - 1
            dataset = run_and_delete(min_parallel, max_parallel, dataset, dataset_params, sys_params, facility_spec)

    if sys_params["run_checkpoint"]:
        dataset["num_evaluated"] = max_parallel
        nrw.save_general_netcdf(dataset, filename_trainingdata)



def run_and_delete(min_parallel, max_parallel, dataset, dataset_params, sys_params, facility_spec):
    run_location = sys_params["root_dir"] + "/" + sys_params["sim_dir"]

    if sys_params["run_plasma_profile"]:
        num_mpi_parallel = int(facility_spec['nbeams'] / facility_spec['beams_per_ifriit_beam'])
    else:
        num_mpi_parallel = 1

    subprocess.check_call(["./bash_parallel_ifriit", run_location, str(min_parallel), str(max_parallel), str(num_mpi_parallel), str(sys_params["num_openmp_parallel"])])

    dataset = nrw.retrieve_xtrain_and_delete(min_parallel, max_parallel, dataset, dataset_params, sys_params, facility_spec)
    return dataset



def run_ifriit_input(num_examples, X_all, run_dir, LMAX, num_parallel, hemisphere_symmetric, run_clean):
    sys_params = define_system_params(run_dir)
    sys_params["num_processes"] = num_parallel
    sys_params["run_clean"] = run_clean # Create new run files

    dataset_params = nrw.read_general_netcdf(sys_params["root_dir"] + "/" + sys_params["dataset_params_filename"])
    facility_spec = nrw.read_general_netcdf(sys_params["root_dir"] + "/" + sys_params["facility_spec_filename"])
    dataset_params["num_examples"] = num_examples
    dataset_params["hemisphere_symmetric"] = hemisphere_symmetric
    dataset_params["Y_train"] = X_all

    generate_training_data(dataset_params, sys_params, facility_spec)

    X_all, Y_all, avg_powers_all = nrw.import_training_data_reversed(sys_params, LMAX)
    return Y_all, avg_powers_all



def main(argv):
    sys_params = define_system_params(argv[1])
    dataset_params, facility_spec = define_dataset_params(int(argv[2]), random_sampling=int(argv[4]), random_seed=int(argv[5]))
    dataset_params["hemisphere_symmetric"] = bool(int(argv[3]))
    generate_training_data(dataset_params, sys_params, facility_spec)

    return dataset_params, sys_params, facility_spec


if __name__ == "__main__":
    _, _, _ = main(sys.argv)
