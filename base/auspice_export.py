from __future__ import division, print_function
import sys, os, time, gzip, glob
from base.io_util import make_dir, remove_dir, tree_to_json, write_json, myopen
import json
from pdb import set_trace
from collections import defaultdict

def process_freqs(frequencies, num_dp):
    """ round frequency estimates to useful precision (reduces file size) """
    return [round(x, num_dp) for x in frequencies]

def export_frequency_json(process, prefix, indent):
    # construct a json file containing all frequency estimate
    # the format is region_protein:159F for mutations and region_clade:123 for clades
    if hasattr(process, 'pivots'):
        freq_json = {'pivots':process_freqs(process.pivots, 4)}
        if hasattr(process, 'mutation_frequencies'):
            freq_json['counts'] = {x:list(counts) for x, counts in process.mutation_frequency_counts.iteritems()}
            for (region, gene), tmp_freqs in process.mutation_frequencies.iteritems():
                for mut, freq in tmp_freqs.iteritems():
                    label_str =  region+"_"+ gene + ':' + str(mut[0]+1)+mut[1]
                    freq_json[label_str] = process_freqs(freq, 4)
        # repeat for clade frequencies in trees
        if hasattr(process, 'tree_frequencies'):
            for region in process.tree_frequencies:
                for clade, freq in process.tree_frequencies[region].iteritems():
                    label_str = region+'_clade:'+str(clade)
                    freq_json[label_str] = process_freqs(freq, 4)
        # repeat for named clades
        if hasattr(process, 'clades_to_nodes') and hasattr(process, 'tree_frequencies'):
            for region in process.tree_frequencies:
                for clade, node in process.clades_to_nodes.iteritems():
                    label_str = region+'_'+str(clade)
                    freq_json[label_str] = process_freqs(process.tree_frequencies[region][node.clade], 4)
        # write to one frequency json
        if hasattr(process, 'tree_frequencies') or hasattr(process, 'mutation_frequencies'):
            write_json(freq_json, prefix+'_frequencies.json', indent=indent)
    else:
        process.log.notify("Cannot export frequencies - pivots do not exist")

def export_tip_frequency_json(process, prefix, indent):
    if not (hasattr(process, 'pivots') and hasattr(process, 'tree_frequencies')):
        process.log.notify("Cannot export tip frequencies - pivots and/or tree_frequencies do not exist")
        return;

    freq_json = {'pivots':process_freqs(process.pivots, 6)}

    clade_tip_map = {n.clade: n.name for n in process.tree.tree.get_terminals()}

    for clade, freq in process.tree_frequencies["global"].iteritems():
        if clade in clade_tip_map:
            freq_json[clade_tip_map[clade]] = process_freqs(freq, 6)

    write_json(freq_json, prefix+'_tip-frequencies.json', indent=indent)

def summarise_publications_from_tree(tree):
    info = defaultdict(lambda: {"n": 0, "title": "?"})
    mapping = {}
    for clade in tree.find_clades():
        if not clade.is_terminal():
            continue
        if "authors" not in clade.attr:
            mapping[clade.name] = None
            print("Error - {} had no authors".format(clade.name))
            continue
        authors = clade.attr["authors"]
        mapping[clade.name] = authors
        info[authors]["n"] += 1
        for attr in ["title", "journal", "paper_url"]:
            if attr in clade.attr:
                info[authors][attr] = clade.attr[attr]
    return (info, mapping)

def extract_annotations(runner):
    annotations = {}
    for name, prot in runner.proteins.iteritems():
        annotations[name] = {
            "start": int(prot.start),
            "end": int(prot.end),
            "strand": prot.strand
        }
    # nucleotides:
    annotations["nuc"] = {
        "start": 1,
        "end": len(str(runner.reference_seq.seq)) + 1
    }
    return annotations;

def export_metadata_json(process, prefix, indent):
    process.log.notify("Writing out metaprocess")
    meta_json = {}

    # count number of tip nodes
    virus_count = 0
    for node in process.tree.tree.get_terminals():
        virus_count += 1
    meta_json["virus_count"] = virus_count

    (author_info, seq_to_author) = summarise_publications_from_tree(process.tree.tree)
    meta_json["author_info"] = author_info
    meta_json["seq_author_map"] = seq_to_author


    # join up config color options with those in the input JSONs.
    col_opts = process.config["auspice"]["color_options"]
    if process.colors:
        for trait, col in process.colors.iteritems():
            if trait in col_opts:
                col_opts[trait]["color_map"] = col
            else:
                process.log.warn("{} in colors (input JSON) but not auspice/color_options. Ignoring".format(trait))

    meta_json["color_options"] = col_opts
    if "date_range" in process.config["auspice"]:
        meta_json["date_range"] = process.config["auspice"]["date_range"]
    if "analysisSlider" in process.config["auspice"]:
        meta_json["analysisSlider"] = process.config["auspice"]["analysisSlider"]
    meta_json["panels"] = process.config["auspice"]["panels"]
    meta_json["updated"] = time.strftime("X%d %b %Y").replace('X0','X').replace('X','')
    meta_json["title"] = process.info["title"]
    meta_json["maintainer"] = process.info["maintainer"]
    meta_json["filters"] = process.info["auspice_filters"]
    meta_json["annotations"] = extract_annotations(process)

    # pass through flu specific information (if present)
    if "vaccine_choices" in process.info:
        meta_json["vaccine_choices"] = process.info["vaccine_choices"]

    if "LBI_params" in process.info:
        meta_json["color_options"]["lbi"] = {
            "key": "LBI",
            "legendTitle": "local branching index",
            "menuItem": "local branching index",
            "tau": process.info["LBI_params"]["tau"],
            "timeWindow": process.info["LBI_params"]["time_window"]
        }

    ## ignore frequency params for now until they are implemented in nextstrain/auspice

    if "defaults" in process.config["auspice"]:
        meta_json["defaults"] = process.config["auspice"]["defaults"]

    try:
        from pygit2 import Repository, discover_repository
        current_working_directory = os.getcwd()
        repository_path = discover_repository(current_working_directory)
        repo = Repository(repository_path)
        commit_id = repo[repo.head.target].id
        meta_json["commit"] = str(commit_id)
    except ImportError:
        meta_json["commit"] = "unknown"
    if len(process.config["auspice"]["controls"]):
        meta_json["controls"] = process.make_control_json(process.config["auspice"]["controls"])
    meta_json["geo"] = process.lat_longs
    write_json(meta_json, prefix+'_meta.json')
