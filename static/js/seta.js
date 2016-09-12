$(function() {
  var input_date = location.search.substr(1).split('=')[1];

  $error = $("#error");
  $body = $("body");


  function loadDate(date) {
    var parts = date.split('/');
    var d = parts[2] + '-' + parts[0] + '-' + parts[1];
    printTable(d);
  }

  function createDates(data) {
    var dates = {};

    //NOTE: dates are in: "2015-01-01 00:00:00" format
    var previous_value = 0;
    var last_date = '';
    for(var val in data) {
      var date = val.split(' ')[0];
      last_date = date;
      var current_value = data[val];

      //TODO: consider doing something different for more/less values
      if (current_value != previous_value) {
        var parts = date.split('-');
        date = parts[1] + '/' + parts[2] + '/' + parts[0];
        dates[new Date(date)] = new Date(date);
      }
      previous_value = current_value;
    }

    $(function() {
      $("#datepicker").datepicker({
        numberOfMonths: 3,
        minDate: new Date(2014, 11-1, 14),
        showButtonPanel: false,
        showOtherMonths: true,
        selectOtherMonths: true,
        onSelect: loadDate,
        beforeShowDay: function(date) {
          var annotated = dates[date];
          if (annotated) {
            return [true, 'annotated', ''];
          } else {
            return [true, '', ''];
          }
        }
      });
    });

    $("#datepicker").datepicker("setDate", "-2m");

    document.getElementById("toggle").addEventListener("click", toggleState);

    if (input_date === undefined || input_date === '') {
      printTable(last_date);
    } else {
      printTable(input_date);
    }
  }

  function printTable(date) {
    $.getJSON("http://seta-dev.herokuapp.com/data/setadetails/?priority=high", {date:date}).done(function (data) { getActiveJobs(data, date); });
  }

  function getActiveJobs(details, date) {
    $.getJSON("http://seta-dev.herokuapp.com/data/jobtypes/").done(function (data) { getTreeNames(data, details, date); });
  }

  function getTreeNames(activeJobs, details, date) {
    $.getJSON("http://seta-dev.herokuapp.com/data/jobnames/").done(function (data) { outputTable(data['results'], activeJobs, details, date); });
  }


  function toggleState() {
    item = document.getElementById("toggle");
    fetchData();
    if (item.value == "Show all Jobs") {
      item.value = "Show required Jobs";
    } else {
      item.value = "Show all Jobs";
    }
  }

  // determine if we need a strike through or not
  function printableJobCode(rawName, partName, osMap) {
    item = document.getElementById("toggle");
    // when item.value == "Hide Optional Jobs", its true value is to "show".
    if (item.value == "Show all Jobs") {
      if (osMap.indexOf(rawName) >= 0) {
        return "<span style='background: white; color: black; font-weight: 14px;'><b>" + partName + " </b></span>";
      }
    }
    else {
      return "<span style='background: white; color: black; font-weight: 14px;'><b>" + partName + " </b></span>";
    }
  }

  function buildOSJobMap(joblist) {
    var map = {};
    // use groupBy to sort joblist by platform and map them into object
    map = _.mapObject(_.groupBy(joblist, function(job) {
      return job[0] + ' ' + job[1];
    }), function(val, key) {
      return val = _.pluck(val, 2)
    });
    return map;
  }

  function outputTable(treenames, active_jobs, details, date) {
      // Get the list of jobs per platform that we don't need to run
      var required_jobs = buildOSJobMap(details['jobtypes'][date]);
      var keys = _.keys(required_jobs);
      if (keys.length == 0) {
          $('#datedesc').replaceWith('<div id="datedesc"><p><h3>Sorry, there is no data for the day ' + date + "</h3></div>");
          $('#seta').html('<table id="seta" border=0></table>');
          return;
      }

      // Get a list of all the active jobs on the tree
      var active_jobs = buildOSJobMap(active_jobs['jobtypes']);

      var mytable = $('#seta');
      var desc = "This is the list of jobs that would be required to run in order to catch every regression in the last 90 days";
      if (mytable.html() === undefined) {
          mytable = $('#seta');
      } else {
          mytable.html('<table id="seta" border=0></table>');
      }
      $('#datedesc').replaceWith('<div id="datedesc">' + date + " - " + desc + "</div>");
      total_jobs = 0;
      high_value_jobs = 0;

      // Iterate through each OS, add a row and colums
      _.each(active_jobs, function(jobs, os) {
          var row = $('<tr></tr>').appendTo(mytable);
          $('<td></td>').text(os).appendTo(row);
          var td_jobs = $('<td></td>').appendTo(row);
          var td_div = $('<div style="float: left"></div>').appendTo(td_jobs);

          var types = {'O': {}}; //Default with other
          _.each(treenames, function(treename) {
              var g = treename['job_group_symbol'];
              if (!(g in types)) {
                  types[g] = {};
              }
          });
          for (var type in types) {
              types[type]['div'] = $('<span></span>').html('').appendTo(td_div);
          }

          // Iterate through all jobs for the given OS, find a group and code
          jobs.sort();
          total_jobs += jobs.length;
          if (os in required_jobs) {
              high_value_jobs += required_jobs[os].length;
          } else{
              required_jobs[os] = [];
          }

        _.each(jobs, function(job) {
            var group = '';
            var jobcode = '';
            _.each(treenames, function(treename) {
                if (treename['name'] == job) {
                    group = treename['job_group_symbol'];
                    jobcode = treename['job_type_symbol'];
                }
            });
            if (jobcode != '' && group == '') {
                group = 'O';
            }

            if (group in types) {
                $('<span></span>').html(printableJobCode(job, jobcode, required_jobs[os])).appendTo(types[group]['div']);
            } else {
                alert("couldn't find matching group: " + group + ", with code: " + jobcode + ": "+ active_osjobs[os][j] + ": " + types);
            }
        });

        // remove empty groups, add group letter and () for visual grouping
        for (var type in types) {
            var leftover = types[type]['div'].html().replace(/\<\/span\>/g, '');
            leftover = leftover.replace(/\<span\>/g, '');

            if (leftover.replace(/ /g, '') == '') {
                types[type]['div'].html('');
            } else if (type != 'O') {
                types[type]['div'].html(type + '(' + leftover.replace(/\s+$/g, '') + ') ');
            }
        }
        var ignore = "Jobs to ignore: " + (total_jobs - high_value_jobs);
        var remaining = "Jobs to run: " + high_value_jobs;
        var total = "Total number of jobs: " + total_jobs;
        $('#jobs_number').replaceWith('<div id="jobs_number">'+ignore+"<br>"+remaining+"<br>"+total+"<div>");

        if (!($('#seta').length)) {
            mytable.appendTo('body');
        } else {
            $('#seta').replaceWith(mytable);
        }
    });
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
    $.getJSON("http://seta-dev.herokuapp.com/data/setasummary/").done(gotsummary).fail(fail);
  }

  $(document).on("ajaxStart ajaxStop", function (e) {
    (e.type === "ajaxStart") ? $body.addClass("loading") : $body.removeClass("loading");
  });

  fetchData();

});
