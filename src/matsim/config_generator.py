"""Generate MATSim config.xml tying together network, plans, and signals."""

import logging
from pathlib import Path

from lxml import etree

logger = logging.getLogger(__name__)


def generate_config(
    network_path: Path,
    plans_path: Path,
    output_dir: Path,
    signal_paths: tuple[Path, Path, Path] | None = None,
    iterations: int = 10,
    sample_rate: float = 0.1,
    end_time_hours: int = 30,
    first_iteration: int = 0,
    write_interval: int = 5,
) -> Path:
    """Generate a MATSim config.xml file.

    Parameters
    ----------
    network_path:
        Path to network.xml.
    plans_path:
        Path to plans.xml.
    output_dir:
        Directory for MATSim output and where config.xml will be written.
    signal_paths:
        Optional tuple of (signalSystems.xml, signalGroups.xml, signalControl.xml).
    iterations:
        Number of MATSim iterations.
    sample_rate:
        Flow/storage capacity factor (e.g. 0.1 for 10% sample).
    end_time_hours:
        Simulation end time in hours (MATSim convention: 30 = 30:00:00).
    first_iteration:
        First iteration number.
    write_interval:
        How often to write output files.

    Returns
    -------
    Path
        Path to the generated config.xml.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    root = etree.Element("config")

    def add_module(name: str) -> etree._Element:
        m = etree.SubElement(root, "module")
        m.set("name", name)
        return m

    def add_param(module: etree._Element, name: str, value: str) -> None:
        p = etree.SubElement(module, "param")
        p.set("name", name)
        p.set("value", value)

    # --- Global ---
    global_mod = add_module("global")
    add_param(global_mod, "coordinateSystem", "EPSG:32654")
    add_param(global_mod, "numberOfThreads", "4")

    # --- Network ---
    network_mod = add_module("network")
    add_param(network_mod, "inputNetworkFile", str(network_path.resolve()))

    # --- Plans ---
    plans_mod = add_module("plans")
    add_param(plans_mod, "inputPlansFile", str(plans_path.resolve()))

    # --- Controler ---
    controler_mod = add_module("controler")
    add_param(controler_mod, "outputDirectory", str((output_dir / "output").resolve()))
    add_param(controler_mod, "firstIteration", str(first_iteration))
    add_param(controler_mod, "lastIteration", str(iterations))
    add_param(controler_mod, "writeEventsInterval", str(write_interval))
    add_param(controler_mod, "writePlansInterval", str(write_interval))
    add_param(controler_mod, "overwriteFiles", "deleteDirectoryIfExists")

    # --- QSim ---
    qsim_mod = add_module("qsim")
    add_param(qsim_mod, "startTime", "00:00:00")
    add_param(qsim_mod, "endTime", f"{end_time_hours}:00:00")
    add_param(qsim_mod, "flowCapacityFactor", f"{sample_rate:.4f}")
    add_param(qsim_mod, "storageCapacityFactor", f"{sample_rate:.4f}")
    add_param(qsim_mod, "numberOfThreads", "4")
    add_param(qsim_mod, "mainMode", "car")
    add_param(qsim_mod, "vehiclesSource", "defaultVehicle")
    add_param(qsim_mod, "trafficDynamics", "queue")
    add_param(qsim_mod, "snapshotperiod", "00:00:00")

    # --- Plan Calc Score ---
    scoring_mod = add_module("planCalcScore")
    add_param(scoring_mod, "learningRate", "1.0")
    add_param(scoring_mod, "BrainExpBeta", "1.0")

    # Activity parameters (home)
    home_params = etree.SubElement(scoring_mod, "parameterset")
    home_params.set("type", "activityParams")
    add_param(home_params, "activityType", "home")
    add_param(home_params, "typicalDuration", "12:00:00")
    add_param(home_params, "minimalDuration", "08:00:00")

    # Activity parameters (work)
    work_params = etree.SubElement(scoring_mod, "parameterset")
    work_params.set("type", "activityParams")
    add_param(work_params, "activityType", "work")
    add_param(work_params, "typicalDuration", "08:00:00")
    add_param(work_params, "minimalDuration", "06:00:00")
    add_param(work_params, "openingTime", "06:00:00")
    add_param(work_params, "closingTime", "22:00:00")

    # --- Strategy ---
    strategy_mod = add_module("strategy")

    # ReRoute
    reroute = etree.SubElement(strategy_mod, "parameterset")
    reroute.set("type", "strategysettings")
    add_param(reroute, "strategyName", "ReRoute")
    add_param(reroute, "weight", "0.2")
    add_param(reroute, "disableAfterIteration", str(int(iterations * 0.8)))

    # ChangeExpBeta (keep best plan)
    keep_best = etree.SubElement(strategy_mod, "parameterset")
    keep_best.set("type", "strategysettings")
    add_param(keep_best, "strategyName", "ChangeExpBeta")
    add_param(keep_best, "weight", "0.7")

    # TimeAllocationMutator
    time_mut = etree.SubElement(strategy_mod, "parameterset")
    time_mut.set("type", "strategysettings")
    add_param(time_mut, "strategyName", "TimeAllocationMutator")
    add_param(time_mut, "weight", "0.1")
    add_param(time_mut, "disableAfterIteration", str(int(iterations * 0.8)))

    # --- Travel Time Calculator ---
    tt_mod = add_module("travelTimeCalculator")
    add_param(tt_mod, "travelTimeBinSize", "900")
    add_param(tt_mod, "maxTime", str(end_time_hours * 3600))

    # --- Signals (if provided) ---
    if signal_paths is not None:
        signals_mod = add_module("signalSystems")
        add_param(signals_mod, "useSignalSystems", "true")
        add_param(signals_mod, "signalsystemsfile", str(signal_paths[0].resolve()))
        add_param(signals_mod, "signalgroupsfile", str(signal_paths[1].resolve()))
        add_param(signals_mod, "signalcontrolfile", str(signal_paths[2].resolve()))
        add_param(signals_mod, "useAmbertimes", "true")
        add_param(signals_mod, "amberTimesFile", "")

    # Write config
    config_path = output_dir / "config.xml"
    tree = etree.ElementTree(root)
    etree.indent(tree, space="  ")
    with open(config_path, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write(b'<!DOCTYPE config SYSTEM "http://www.matsim.org/files/dtd/config_v2.dtd">\n')
        tree.write(f, pretty_print=True, xml_declaration=False, encoding="UTF-8")

    logger.info("Wrote MATSim config → %s", config_path)
    return config_path
