$(function() {
  $error = $("#error"),
  $body = $("body");

  //TODO: consider revisiting this to ensure we have accurate data and the right format/presentations
  function createDates(data) {
    var s = $('<select />');

    data.sort;

    var count = 0;
    var length = 0;
    for (var val in data) {
       length++;
    }

    var baseline = 0;
    var lastDate = 0;
    for(var val in data) {
      date = val.split(' ')[0];
      count++;
      if (count == 1) {
          baseline = parseInt(data[val]);
          text = date + " (removed: " + baseline + ")";
      } else {
          text = date + " (changed: " + (parseInt(data[val]) - baseline) + ")";
      }
      if (count == length) {
          $('<option />', {value: val, text:text, selected:'selected'}).appendTo(s);
          lastDate = val;
      } else {
          $('<option />', {value: val, text:text}).appendTo(s);
      }
    }
    s.appendTo('body');

    printTable(lastDate);
  }



  function printTable(date) {
    $.getJSON("/data/setadetails/", {date:date}).done(function (data) { getActiveJobs(data, date); });
  }

  function getActiveJobs(details, date) {
    $.getJSON("/data/jobtypes/").done(function (data) { outputTable(data, details, date); });
  }

  // Simple text replace of full names -> Group-Code format
  function printName(testname) {
    var retVal = testname.replace(/mochitest-browser-chrome[-]?/, 'M-bc');
    retVal = retVal.replace(/mochitest-e10s-browser-chrome[-]?/, 'Me10s-bc');
    retVal = retVal.replace(/mochitest-e10s-devtools-chrome[-]?/, 'M-dt');
    retVal = retVal.replace('mochitest-e10s', 'Me10s');
    retVal = retVal.replace(/mochitest-devtools-chrome[-]?/, 'M-dt');
    retVal = retVal.replace('mochitest-other', 'M-oth');
    retVal = retVal.replace('mochitest', 'M');
    retVal = retVal.replace('crashtest-ipc', 'R-C-ipc');
    retVal = retVal.replace('crashtest', 'R-C');
    retVal = retVal.replace('jsreftest', 'R-J');
    retVal = retVal.replace('reftest-no-accel', 'R-RU');
    retVal = retVal.replace('reftest-e10s', 'Re10s-R');
    retVal = retVal.replace('reftest', 'R-R');
    retVal = retVal.replace('xpcshell', 'O-X');
    retVal = retVal.replace('marionette', 'O-Mn');
    retVal = retVal.replace('cppunit', 'O-Cpp');
    retVal = retVal.replace(/jittest[-]?/, 'O-Jit');
    retVal = retVal.replace('web-platform-tests', 'WPT');
    return retVal;
  }

  function fixPlatform(plat) {
    retVal = plat.replace('osx10.6', 'osx-10-6');
    retVal = retVal.replace('osx10.8', 'osx-10-8');
    retVal = retVal.replace('winxp', 'windowsxp');
    retVal = retVal.replace('win7', 'windows7-32');
    retVal = retVal.replace('win8', 'windows8-64');

    return retVal
  }

  // determine if we need a strike through or not
  // TODO: add features to toggle on off
  function jobCode(rawName, partName, osMap) {
    if (osMap.indexOf(rawName) >= 0) {
        return "<span style='color: grey'>" + partName + " </span>";
    } else {
        return "<span style='color: green'><b>" + partName + " </b></span>";
    }
  }

  function buildOSJobMap(joblist) {
    var map = {}

    for (var i = 0; i < joblist.length; i++) {
      var job = joblist[i];
      key = fixPlatform(job[0]) + " " + job[1];
      if (map[key] === undefined) {
          map[key] = [];
      }
      map[key].push(job[2]);
    }
    return map;
  }

  function outputTable(active_jobs, details, date) {

    // For some reason we don't have windows8 bits in the list and need it
    var optional_jobs = buildOSJobMap(details['jobtypes'][date]);
    optional_jobs['windows8-64 debug'] = []
    optional_jobs['windows8-64 opt'] = []

    // Get a list of all the active jobs on the tree
    var active_osjobs = buildOSJobMap(active_jobs['jobtypes']);

    var active_oslist = ['linux32 opt', 'linux32 debug',
                         'linux64 opt', 'linux64 asan', 'linux64 debug',
                         'osx-10-6 opt', 'osx-10-6 debug',
                         'osx-10-8 opt', 'osx-10-8 debug',
                         'windowsxp opt', 'windowsxp debug',
                         'windows7-32 opt', 'windows7-32 debug',
                         'windows8-64 opt', 'windows8-64 debug'];

    var mytable = $('<table></table>').attr({id:'seta', border: 0});

    // Iterate through each OS, add a row and colums
    for (var i = 0; i < active_oslist.length; i++) {
      var os = active_oslist[i];
      var row = $('<tr></tr>').appendTo(mytable);
      $('<td></td>').text(os).appendTo(row);
      var td_jobs = $('<td></td>').appendTo(row);
      var td_div = $('<div style="float: left"></div>').appendTo(td_jobs);

      var types = { 'O': {'group': 'O'},
                    'M': {'group': 'M'}, "Me10s": {'group': 'M-e10s'},
                    'R': {'group': 'R'}, 'Re10s': {'group': 'R-e10s'},
                    'WPT': {'group': 'W'}}

      for (var type in types) {
          types[type]['div'] = $('<span></span>').html('').appendTo(td_div);
      }


      // Iterate through all jobs for the given OS, find a group and code
      active_osjobs[os].sort();
      for (var j = 0; j < active_osjobs[os].length; j++) {
        var jobparts = printName(active_osjobs[os][j]).split('-', 2);
        var group = jobparts[0];
        var jobcode = jobparts[1];

        if (group in types) {
          $('<span></span>').html(jobCode(active_osjobs[os][j], jobcode, optional_jobs[os])).appendTo(types[group]['div']);
        } else {
          alert("couldn't find matching group: " + group + ", with code: " + jobcode);
        }
      }

      // remove empty groups, add group letter and () for visual grouping
      for (var type in types) {
        var leftover = types[type]['div'].html().replace(/\<\/span\>/g, '');
        leftover = leftover.replace(/\<span\>/g, '');

        if (leftover.replace(/ /g, '') == '') {
            types[type]['div'].html('');
        } else if (type != 'O') {
           types[type]['div'].html(types[type]['group'] + '(' + leftover.replace(/\s+$/g, '') + ') ');
        }
      }

    }
    mytable.appendTo('body');
  }

  function gotsummary(data) {
    if ($error.is(":visible")) $error.hide();
    createDates(data.dates);
  }

  function fail(error) {
    $dates.hide();
    $error.text(error).show();
  }

  function fetchData(e) {
    if (e) e.preventDefault();
    $.getJSON("/data/setasummary/").done(gotsummary).fail(fail);
  }

  $(document).on("ajaxStart ajaxStop", function (e) {
    (e.type === "ajaxStart") ? $body.addClass("loading") : $body.removeClass("loading");
  });

  fetchData();

});
