import React, { Component, useEffect, useReducer, useState } from 'react';
import Checkbox from '@mui/material/Checkbox';
import TreeView from '@mui/lab/TreeView';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import TreeItem from '@mui/lab/TreeItem';
import { domains } from './fakeData';

const checkMap = {
  2: 'checked',
  1: 'partChecked',
  0: ''
}

const getMockData = () => {
  let resData = JSON.parse(JSON.stringify(domains.domains));
  const travelChildren = (domain, index) => {
    domain.children.forEach((childDomain, childIndex) => {
      childDomain.id = index.toString() + childIndex.toString();
      childDomain.checked = 0;
      travelChildren(childDomain, index.toString() + childIndex.toString());
    })
  }
  resData.forEach((domain, index) => {
    domain.id = index.toString();
    domain.checked = 0;
    travelChildren(domain, index);
  })
  return resData;
};

const mockData = getMockData();

// const label = { inputProps: { 'aria-label': 'Checkbox demo' } };

const TreeNode = ({ label, id, checked, onSelect }) => {
  return (
      <div>
          <Checkbox id={id} checked={checked? true: false} onChange={(e) => onSelect(e)} />
          <label>{label}</label>
      </div>
  )
}

export function TreeNodeComp() {
  const [treeData, setTreeData] = useState(mockData);
  const [selectedId, setSelectedId] = useState([]);
  
  const updateSelectedNode = (tree_data, id, isChecked, deepth) => {
    const parentId = id.slice(0, -1);
    function findParentNode (node) {
      for(const childNode of node) {
        if(childNode.id === parentId) return childNode;
        else {
          const res = findParentNode(childNode.children);
          if(res) return res;
        }
      }
    }
    if(!parentId) {
      const node = tree_data.find((node) => node.id === id);
      node.checked = isChecked;
      if(deepth === 0) updateChildrenNodes(node, isChecked);
      return;
    } 
    const parentNode = findParentNode(tree_data);
    const childrenNodes = parentNode.children;
    if(deepth === 0) {
      const node = childrenNodes.find((node) => node.id === id);
      updateChildrenNodes(node, isChecked);
    }
    if(isChecked) {
      let allChildrenChecked = true;
      childrenNodes.forEach((node) => {
        if (node.id === id) node.checked = isChecked;
        else if(node.checked !== 2) allChildrenChecked = false;
      })
      if (allChildrenChecked) parentNode.checked = 2;
      else parentNode.checked = 1;
    } else {
      let allChildrenNotChecked = true;
      childrenNodes.forEach((node) => {
        if(node.id === id) node.checked = isChecked;
        else if(node.checked !== 0) allChildrenNotChecked = false;
      })
      if (allChildrenNotChecked) parentNode.checked = 0;
      else parentNode.checked = 1;
    }
    updateSelectedNode(tree_data, parentId, parentNode.checked, ++deepth);
  }

  const updateChildrenNodes = (node, isChecked) => {
    node.children.forEach((childNode) => {
      childNode.checked = isChecked;
      updateChildrenNodes(childNode, isChecked);
    })
  }

  // const findSelectedNode = (tree_data, id) => {
  //   for(const childNode of tree_data) {
  //     if(childNode.id === id) return childNode;
  //     else {
  //       const res = findSelectedNode(childNode.children, id);
  //       if(res) return res;
  //     }
  //   }
  // }

  const handleOnSelect = (event) => {
    const id = event.target.id;
    const isChecked = event.target.checked;
    const tempTreeData = JSON.parse(JSON.stringify(treeData));

    setTreeData((prevTreeData) => {
      const tempTreeData = JSON.parse(JSON.stringify(prevTreeData));
      updateSelectedNode(tempTreeData, id, isChecked?2:0, 0);
      return tempTreeData;
    })
  }

  const renderNode = (node) => {
    const { id, checked, name } = node;

    return (
      <TreeItem key={id} nodeId={id} label={<TreeNode label={name} id={id} checked={checked} onSelect={handleOnSelect} />}>
        {node.children.map((childNode) => {
          return renderNode(childNode);
        })}
      </TreeItem>
    )
  }

  return (
    <TreeView
      aria-label="multi-select"
      defaultCollapseIcon={<ExpandMoreIcon />}
      defaultExpandIcon={<ChevronRightIcon />}
      sx={{ height: 216, flexGrow: 1, maxWidth: 400, overflowY: 'auto' }}
    >
      {treeData.map((node) => renderNode(node))}
      {/* <TreeItem nodeId="1" label={<TreeItemContent content="Applications" />}>
        <TreeItem nodeId="22" label="Calendar" />
        <TreeItem nodeId="3" label="Chrome" />
        <TreeItem nodeId="4" label="Webstorm" />
      </TreeItem>
      <TreeItem nodeId="5" label="Documents">
        <TreeItem nodeId="6" label="MUI">
          <TreeItem nodeId="7" label="src">
            <TreeItem nodeId="8" label="index.js" />
            <TreeItem nodeId="9" label="tree-view.js" />
          </TreeItem>
        </TreeItem>
      </TreeItem> */}
    </TreeView>
  );
}


// export const TreeNodeComp = () => {
//     return (
//         <TreeItemContent content='hello' />
//     )
// }