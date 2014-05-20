// File: tablesort.js		-*- JavaScript -*- 
// Created by: Alex Knowles (ark@google.com) Wed May  4 17:31:16 2005
// Last Modified: Time-stamp: <Wed May  4 17:31:19 PDT 2005> 
// $Id: tablesort.js,v 1.1 2006-03-08 18:45:07 ark Exp $ 

//////////////////////////////////////////////////////////////////////
// from http://www.brainjar.com/dhtml/tablesort/demo.html
// I modified this code only to allow multipliers (G, M, K) on numeric values
// and also to look at the sortvalue attribute and use that if present

//-----------------------------------------------------------------------------
// sortTable(id, col, rev)
//
//  id  - ID of the TABLE, TBODY, THEAD or TFOOT element to be sorted.
//  col - Index of the column to sort, 0 = first column, 1 = second column,
//        etc.
//  rev - If true, the column is sorted in reverse (descending) order
//        initially.
//
// Note: the team name column (index 1) is used as a secondary sort column and
// always sorted in ascending order.
//-----------------------------------------------------------------------------

function sortTable(id, col, rev) {

  // Get the table or table section to sort.
  var tblEl = document.getElementById(id);

  // The first time this function is called for a given table, set up an
  // array of reverse sort flags.
  if (tblEl.reverseSort == null) {
    tblEl.reverseSort = new Array();
    // Also, assume the team name column is initially sorted.
    tblEl.lastColumn = 1;
  }

  // If this column has not been sorted before, set the initial sort direction.
  if (tblEl.reverseSort[col] == null)
    tblEl.reverseSort[col] = rev;

  // If this column was the last one sorted, reverse its sort direction.
  if (col == tblEl.lastColumn)
    tblEl.reverseSort[col] = !tblEl.reverseSort[col];

  // Remember this column as the last one sorted.
  tblEl.lastColumn = col;

  // Set the table display style to "none" - necessary for Netscape 6 
  // browsers.
  var oldDsply = tblEl.style.display;
  tblEl.style.display = "none";

  // Sort the rows based on the content of the specified column using a
  // selection sort.

  var tmpEl;
  var i, j;
  var minVal, minIdx;
  var testVal;
  var cmp;

  for (i = 0; i < tblEl.rows.length - 1; i++) {

    // Assume the current row has the minimum value.
    minIdx = i;
    minVal = getTextValue(tblEl.rows[i].cells[col]);

    // Search the rows that follow the current one for a smaller value.
    for (j = i + 1; j < tblEl.rows.length; j++) {
      testVal = getTextValue(tblEl.rows[j].cells[col]);
      cmp = compareValues(minVal, testVal);
      // Negate the comparison result if the reverse sort flag is set.
      if (tblEl.reverseSort[col])
        cmp = -cmp;
      // Sort by the second column (team name) if those values are equal.
      if (cmp == 0 && col != 1)
        cmp = compareValues(getTextValue(tblEl.rows[minIdx].cells[1]),
                            getTextValue(tblEl.rows[j].cells[1]));
      // If this row has a smaller value than the current minimum, remember its
      // position and update the current minimum value.
      if (cmp > 0) {
        minIdx = j;
        minVal = testVal;
      }
    }

    // By now, we have the row with the smallest value. Remove it from the
    // table and insert it before the current row.
    if (minIdx > i) {
      tmpEl = tblEl.removeChild(tblEl.rows[minIdx]);
      tblEl.insertBefore(tmpEl, tblEl.rows[i]);
    }
  }

  // Make it look pretty.
  makePretty(tblEl, col);

  // Restore the table's display style.
  tblEl.style.display = oldDsply;

  return false;
}

//-----------------------------------------------------------------------------
// Functions to get and compare values during a sort.
//-----------------------------------------------------------------------------

// This code is necessary for browsers that don't reflect the DOM constants
// (like IE).
if (document.ELEMENT_NODE == null) {
  document.ELEMENT_NODE = 1;
  document.TEXT_NODE = 3;
}

function getTextValue(el) {

  var i;
  var s;

  i = el.getAttribute("sortvalue"); 
  if (i) {
    return i;
  }

  // Find and concatenate the values of all text nodes contained within the
  // element.
  s = "";
  for (i = 0; i < el.childNodes.length; i++)
    if (el.childNodes[i].nodeType == document.TEXT_NODE)
      s += el.childNodes[i].nodeValue;
    else if (el.childNodes[i].nodeType == document.ELEMENT_NODE &&
             el.childNodes[i].tagName == "BR")
      s += " ";
    else
      // Use recursion to get text within sub-elements.
      s += getTextValue(el.childNodes[i]);

  return normalizeString(s);
}

// If the values are numeric, convert them to floats.
// we allow multipliers on the string too G = gig M = meg
function getVal( s ) {
  var f = parseFloat(s);
  if (!isNaN(f)) {
    switch (s.substring(s.length-1)) {
    case 'G': f *= 1000000000; break;
    case 'M': f *= 1000000; break;
    case 'K': f *= 1000; break;
    }
    return f;
  }
  return s;
}

function compareValues(v1, v2) {
  v1 = getVal(v1);
  v2 = getVal(v2);
  
  // Compare the two values.
  if (v1 == v2)
    return 0;
  if (v1 > v2)
    return 1
  return -1;
}

// Regular expressions for normalizing white space.
var whtSpEnds = new RegExp("^\\s*|\\s*$", "g");
var whtSpMult = new RegExp("\\s\\s+", "g");

function normalizeString(s) {

  s = s.replace(whtSpMult, " ");  // Collapse any multiple whites space.
  s = s.replace(whtSpEnds, "");   // Remove leading or trailing white space.

  return s;
}

//-----------------------------------------------------------------------------
// Functions to update the table appearance after a sort.
//-----------------------------------------------------------------------------

// Style class names.
var rowClsNm = "alternateRow";
var colClsNm = "sortedColumn";

// Regular expressions for setting class names.
var rowTest = new RegExp(rowClsNm, "gi");
var colTest = new RegExp(colClsNm, "gi");

function makePretty(tblEl, col) {

  var i, j;
  var rowEl, cellEl;

  // Set style classes on each row to alternate their appearance.
  for (i = 0; i < tblEl.rows.length; i++) {
   rowEl = tblEl.rows[i];
   rowEl.className = rowEl.className.replace(rowTest, "");
    if (i % 2 != 0)
      rowEl.className += " " + rowClsNm;
    rowEl.className = normalizeString(rowEl.className);
    // Set style classes on each column (other than the name column) to
    // highlight the one that was sorted.
    for (j = 2; j < tblEl.rows[i].cells.length; j++) {
      cellEl = rowEl.cells[j];
      cellEl.className = cellEl.className.replace(colTest, "");
      if (j == col)
        cellEl.className += " " + colClsNm;
      cellEl.className = normalizeString(cellEl.className);
    }
  }

  // Find the table header and highlight the column that was sorted.
  var el = tblEl.parentNode.tHead;
  if (el) {
    rowEl = el.rows[el.rows.length - 1];
    // Set style classes for each column as above.
    for (i = 0; i < rowEl.cells.length; i++) {
      cellEl = rowEl.cells[i];
      cellEl.className = cellEl.className.replace(colTest, "");
      // Highlight the header of the sorted column.
      if (i == col)
        cellEl.className += " " + colClsNm;
      cellEl.className = normalizeString(cellEl.className);
    }
  }
}

function setRanks(tblEl, col, rev) {

  // Determine whether to start at the top row of the table and go down or
  // at the bottom row and work up. This is based on the current sort
  // direction of the column and its reversed flag.

  var i    = 0;
  var incr = 1;
  if (tblEl.reverseSort[col])
    rev = !rev;
  if (rev) {
    incr = -1;
    i = tblEl.rows.length - 1;
  }

  // Now go through each row in that direction and assign it a rank by
  // counting 1, 2, 3...

  var count   = 1;
  var rank    = count;
  var curVal;
  var lastVal = null;

  // Note that this loop is skipped if the table was sorted on the name
  // column.
  while (col > 1 && i >= 0 && i < tblEl.rows.length) {

    // Get the value of the sort column in this row.
    curVal = getTextValue(tblEl.rows[i].cells[col]);

    // On rows after the first, compare the sort value of this row to the
    // previous one. If they differ, update the rank to match the current row
    // count. (If they are the same, this row will get the same rank as the
    // previous one.)
    if (lastVal != null && compareValues(curVal, lastVal) != 0)
        rank = count;
    // Set the rank for this row.
    tblEl.rows[i].rank = rank;

    // Save the sort value of the current row for the next time around and bump
    // the row counter and index.
    lastVal = curVal;
    count++;
    i += incr;
  }

  // Now go through each row (from top to bottom) and display its rank. Note
  // that when two or more rows are tied, the rank is shown on the first of
  // those rows only.

  var rowEl, cellEl;
  var lastRank = 0;

  // Go through the rows from top to bottom.
  for (i = 0; i < tblEl.rows.length; i++) {
    rowEl = tblEl.rows[i];
    cellEl = rowEl.cells[0];
    // Delete anything currently in the rank column.
    while (cellEl.lastChild != null)
      cellEl.removeChild(cellEl.lastChild);
    // If this row's rank is different from the previous one, Insert a new text
    // node with that rank.
    if (col > 1 && rowEl.rank != lastRank) {
      cellEl.appendChild(document.createTextNode(rowEl.rank));
      lastRank = rowEl.rank;
    }
  }
}

