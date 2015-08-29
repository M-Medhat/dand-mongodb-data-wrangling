# -*- coding: utf-8 -*
from collections import defaultdict
import xml.etree.cElementTree as ET
import pprint
import re
import codecs
import json

lower = re.compile(r'^([a-z]|_)*$')
lower_colon = re.compile(r'^([a-z]|_)*:([a-z]|_)*$')
problemchars = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n]')
en_street_type_re = re.compile(r'\b\S+\.?$', re.IGNORECASE)
# street type appear at the beginning in Arabic
ar_street_type_re = re.compile(r'^\S+\b\.?', re.UNICODE)

# Arabic part => [Shara', Midan, Tariq, Mehwar, Al-Mehwar, Kornish, Migawrah, Imtidad]
expected = ["Street", "Avenue", "Boulevard",
               "Drive", "Court", "Place",
               "Square", "Lane", "Road",
               "Trail", "Parkway", "Commons",
              u"شارع", u"ميدان", u"طريق",
              u"محور", u"المحور", u"كورنيش",
              u"مجاورة", u"امتداد"]

en_mapping = { "St": "Street",
            "St.": "Street",
            "Rd.": "Road",
            "Rd" : "Road",
            "Ave": "Avenue"
            }

CREATED = [ "version", "changeset", "timestamp", "user", "uid"]

def count_tags(filename):
  """
  Counts the number of occurraces for each tag in the document.

  Args:
    filename: the path to the XML document
  Returns:
    tags: A dictionary of tag names as keys and counts as values
  """
  tags = {}
  for event, elem in ET.iterparse(filename):
    if elem.tag in tags:
      tags[elem.tag] += 1
    else:
      tags[elem.tag] = 1
            
  return tags


def key_type(element, keys):
  """
  Increments the correct entry in keys dictionary for the element tag.
  It updates the entries if element.tag == 'tag'

  Args:
    element: the element to check its key
    keys: keys dictionary with categories as key and counts as values
  Returns:
    keys: keys dictionary with categories as key and counts as values
  """
  if element.tag == "tag":
    key = element.attrib['k']

    if re.match(lower, key) != None:
      keys["lower"] += 1
    elif re.match(lower_colon, key) != None:
      keys["lower_colon"] += 1
    elif re.match(problemchars, key) != None:
      keys["problemchars"] += 1
    else:
      keys["other"] += 1
        
  return keys


def check_keys(filename):
  """
  Counts the number of occurrances of keys for each category (
	lower case, lower case with colon, has problematic characters,
    other)

  Args:
    filename: path to the XML document
  Returns:
    keys: A dictionary of key types, with category as key and count as value
  """
  keys = {"lower": 0, "lower_colon": 0, "problemchars": 0, "other": 0}
  for _, element in ET.iterparse(filename):
    keys = key_type(element, keys)

  return keys


def audit_street_type(street_types, street_name):
  """
  Checks whether a street name is of an expected format

  Args:
    street_types: the dictionary to append found format to
    street_name: the name of the street to audit
  """
  if isinstance(street_name, unicode): # if Arabic
	m = ar_street_type_re.search(street_name)
  else: # if English
    m = en_street_type_re.search(street_name)

  if m:
    street_type = m.group()
    if street_type not in expected:
      street_types[street_type].add(street_name)


def is_street_name(elem):
  """
  Checks if the given element contains a street name
  
  Args:
    elem: the element to check
  Returns:
    is_street_name: a boolean indicating if it contains a street name
  """
  return (elem.attrib['k'] == "addr:street")


def audit(osmfile):
  """
  Audits an OSM XML file for street names

  Args:
    osmfile: the input OSM XML file
  Returns:
    street_types: a dictionary of available street formats in the document
  """
  osm_file = open(osmfile, "r")
  street_types = defaultdict(set)
  for event, elem in ET.iterparse(osm_file, events=("start",)):
    if elem.tag == "node" or elem.tag == "way": # process only node and way tags
      for tag in elem.iter("tag"): # which hava a "tag" tag inside them. 
        if is_street_name(tag):
          audit_street_type(street_types, tag.attrib['v'])

  return street_types


def update_street_name(name, mapping):
  """
  Enhance street name by normalizing types. and adds the word street in 
  Arabic (شارع) the street names that are missing it.

  Args:
    name: the name of the street
    mapping: a dictionary mapping abbrivations to correct forms
  Returns:
   name: enhanced street name
  """
  if isinstance(name, unicode): # if arabic
    # street type is at the beginning
    t = name.split(" ")[0]
    if t not in expected:
      name = u"شارع " + name
  else:
    for k, v in mapping.iteritems():
      if name.endswith(k):
        name = name.replace(k, v)

  return name

def shape_element(element):
  """
  Shapes an OSM XML element into the following format:
  {
  "id": "2406124091",
  "type: "node",
  "visible":"true",
  "created": {
    "version":"2",
    "changeset":"17206049",
    "timestamp":"2013-08-03T16:43:42Z",
    "user":"linuxUser16",
    "uid":"1219059"
  },
  "pos": [41.9757030, -87.6921867],
  "address": {
    "housenumber": "5157",
    "postcode": "60625",
    "street": "North Lincoln Ave"
  },
  "amenity": "restaurant",
  "cuisine": "mexican",
  "name": "La Cabana De Don Luis",
  "phone": "1 (773)-271-5176"
  }

  Args:
    element: the element to format
  Returns:
    node: a dictionary of the explained format
  """
  node = {}
  if element.tag == "node" or element.tag == "way" : # process only node and way tags
    node["type"] = element.tag
    node["created"] = {}
    for k,v in element.attrib.iteritems(): # process element attributes
      if k in CREATED: # if the attribute name is in the list "CREATED"
        node["created"][k] = v
      elif k in ["lon", "lat"]: # if lat or lon add it to pos list
        node["pos"] = [ float(element.attrib["lat"]), float(element.attrib["lon"])]
      else:
        node[k] = v
        
    node["node_refs"] = []
    node["address"] = {}
    for child in element:
      if child.tag == "tag": # process "tag" tags; the children.
        i = child.attrib["k"]
        j = child.attrib["v"]

        # if the key has a problematic char, ignor it
        if (re.match(problemchars, i) != None): 
          continue
        elif i.startswith("addr:"): 
          # if it's an address with more than one colon, ignore it
          if len(i.split(":")) > 2:
            continue
          # if it's an address with one colon add it to address dictionary
          else:
            key = i.split(":")[1]
            if key == "street":
              j = update_street_name(j, en_mapping)
            node["address"][key] = j
        else:
          node[i] = j

      # process nd tags
      elif child.tag == "nd":
        node["node_refs"].append(child.attrib["ref"])
      
    # if node_refs is an empty list delete it from the node
    if node["node_refs"] == []:
      del node["node_refs"]
          
    # if the address is an empty dictionary, remove it from the node
    if node["address"] == {}:
      del node["address"]

    return node
  else:
    return None


def process_map(file_in, pretty = False):
  """
  Converts an OSM XML file into JSON file after creating the correct format
  and cleaning the data.

  Args:
    file_in: the input OSM XML file
    pretty: whether to output the JSON data as pretty or not. default false.
  Returns:
   data: dictionary of data in the correct format.
  """
  file_out = "{0}.json".format(file_in)
  data = []
  with codecs.open(file_out, "w") as fo:
    for _, element in ET.iterparse(file_in):
      el = shape_element(element)
      if el:
        data.append(el)
        if pretty:
          fo.write(json.dumps(el, indent=2, ensure_ascii=False).encode('utf-8')+"\n")
        else:
          fo.write(json.dumps(el, ensure_ascii=False).encode('utf-8') + "\n")

  return data


class MyPrettyPrinter(pprint.PrettyPrinter):
  """
  A modified Pretty Printer to display unicode characters correctly

  http://stackoverflow.com/a/10883893/569827
  """
  def format(self, object, context, maxlevels, level):
    if isinstance(object, unicode):
      return (object.encode('utf8'), True, False)
    return pprint.PrettyPrinter.format(self, object, context, maxlevels, level)


def main():
  data_file_path = 'data/cairo_egypt.osm'

  print "\nCairo, Egypt OSM Data Analysis"
  print "\nPlease choose a function:"
  print "\t1. Count Tags in OSM XML file"
  print "\t2. Check key types"
  print "\t3. Audit Street Names"
  print "\t4. Clean Data and Convert to JSON"
  print "\t5. Load JSON file to MongoDB"
  print "\t6. Create Summaries about Data"

  operation = raw_input()

  # Count Tags in OSM XML file
  if int(operation) == 1:
    print "Counting tags in OSM XML file ..."
    tags = count_tags(data_file_path)
    pprint.pprint(tags)

  elif int(operation) == 2: # Check Key types
    print "Checking key types ..."
    keys = check_keys(data_file_path)
    pprint.pprint(keys)

  elif int(operation) == 3: # Audit Street Names
    print "Auditing Street Names ..."
    street_types = audit(data_file_path)
    MyPrettyPrinter().pprint(dict(street_types))

  elif int(operation) == 4: # Clean Data and Convert to JSON
    print "Cleaning and Converting to JSON ..."
    data = process_map(data_file_path, False)
    MyPrettyPrinter().pprint(data[0])

  elif int(operation) == 5: # Load JSON file to MongoDB
    print "Importing JSON data to MongoDB ..."
    pass

  elif int(operation) == 6: # Create summaries about the data
    print "Creating Summaries ..."
    pass

  else:
    print "Invalid Operation"

if __name__ == "__main__":
  main()
